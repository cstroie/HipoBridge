# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the server

```bash
export HYP_USER=<username> HYP_PASS=<password>
python3 hipobridge.py
```

Server listens on `http://0.0.0.0:44660` by default. Override with `local.cfg`:

```ini
[server]
port = 8080

[hipocrate]
service_url = http://192.168.3.230/hipocrate
```

`local.cfg` takes precedence over `hipobridge.cfg` and is not tracked by git.

## Running tests

```bash
python3 runtests.py               # all tests
python3 runtests.py extractors    # one group (no server needed)
python3 runtests.py markdown      # one group (no server needed)
python3 runtests.py hipodata      # one group (no server needed)
```

Groups that don't hit the network: `extractors`, `markdown`, `hipodata`.  
Groups that need a live server + credentials: `root`, `auth`, `patients`, `analyses`, `reports`, `checkout`, `cnp`.

## Architecture

HippoBridge is a **scraping proxy**: it has no database. Every request authenticates against Hipocrate, scrapes HTML, and returns structured JSON or FHIR R4 resources.

### Request flow

```
HTTP client
  → hipobridge.py       (aiohttp routes + @require_auth decorator)
  → HipoClient*         (fetches Hipocrate HTML through cache + semaphore)
  → fhir.py             (converts HipoData → FHIR resource)
  → web_fhir_response / web_json_response
```

### Key modules

**`hipobridge.py`** — entry point. Defines all routes and two response helpers:
- `web_json_response` — raw internal API (`/api/*`)
- `web_fhir_response` — FHIR-typed responses (`/fhir/*`); handles `OperationOutcome` on errors
- `@require_auth` decorator extracts Basic Auth and attaches credentials to `request.auth_credentials`

**`hipoclient.py`** — the core scraping layer. One base class + seven specialised subclasses:

| Class | Resource |
|---|---|
| `HipoClient` | Base: session management, fetch, cache, semaphore, auth |
| `HipoClientPatient` | Patient record page |
| `HipoClientPatientSearch` | Patient search results |
| `HipoClientServiceRequest` | Individual exam/service request |
| `HipoClientServiceRequestSearch` | Service request list for a patient |
| `HipoClientImagingStudy` | Imaging study report |
| `HipoClientDiagnosticReport` | Diagnostic report |
| `HipoClientCheckout` | Discharge/encounter summary |

Every subclass implements three methods:
- `fetch_and_parse(**kwargs)` → `HipoData` (raw dict)
- `fhir_response(parsed_data)` → FHIR resource object
- `fetch_respond_fhir(**kwargs)` → calls both, returns FHIR resource directly

**Concurrency and caching** (critical — Hipocrate is a fragile legacy server):
- `_hipocrate_semaphore = asyncio.Semaphore(6)` — global cap on concurrent outbound HTTP calls; all request paths including login go through this.
- `URLCache` (`urlcache.py`) — true LRU cache (`OrderedDict`), 500 entries, 30-minute TTL. In-flight deduplication via `asyncio.Event`: if two coroutines miss the cache for the same URL simultaneously, the second waits for the first's result rather than issuing a duplicate request. `resolve_inflight()` must be called on **every** exit path (including re-auth failures) or waiters hang permanently.
- `UserSessionManager` — one `aiohttp.ClientSession` per username (cookie reuse). Includes a per-user `asyncio.Lock` so concurrent requests from the same user never trigger two simultaneous login sequences. Tracks `is_authenticated` state to skip redundant Hipocrate probes.
- `login_if_needed(force=True)` — skip the is-logged-in main.asp probe when the caller already knows the session is expired.
- `DICOM_MODALITY` — module-level dict mapping internal type codes (`radio`, `eco`, `ct`, `mri`) to `(DICOM_code, human_display)` tuples. Use this for both top-level and per-series modality fields in `ImagingStudy`; never repeat the code string as the display value.

**`fhir.py`** — FHIR R4 resource model. `Resource(MutableMapping)` is the base; all FHIR types subclass it. Key behaviours:
- `Resource.__setitem__(key, None)` removes the key (never stores `None`).
- `to_dict()` recurses into nested plain dicts so `Resource` objects inside dict values are serialised correctly.
- `OperationOutcome.from_error()` default `code` is `"processing"` (a valid FHIR issue code). Always pass an explicit `code` for `"not-found"`, `"required"`, etc.
- `Bundle.append_entry()` keeps `total` in sync with the actual entry count.
- `Encounter` uses FHIR R4 field names: `period`, `reasonCode`, `reasonReference`, `hospitalization` — not the R5 names (`actualPeriod`, `businessStatus`, etc.).

**`hipodata.py`** — `HipoData(dict)` typed dict wrapper passed between the scraper and the FHIR converter.
- `store(key, value)` normalises values via `_normalise()`: strips strings, unwraps single-item lists, converts `datetime` → ISO string, skips `None`. Dot-notation keys (`"patient.id"`) create nested dicts automatically. Empty section or sub-key after the dot is silently ignored.
- `store_list(key, value)` — like `store()` but always keeps the value as a list; also skips `None`.
- `get(key, default=None)` — default is `None` (matching `dict.get`). Callers that need `""` must pass it explicitly.
- `set(key, value)` — same normalisation as `store()` (strings stripped, datetimes converted).
- `__init__(**kwargs)` routes all kwargs through `store()` so construction-time values are normalised.
- `set_success()` removes the `message` key rather than setting it to `""`.

**`extractors.py`** — stateless HTML-parsing helpers: `extract_text_after_label`, `extract_id_from_link`, `extract_ids_from_links`, `parse_cnp`, `parse_date_time`, etc.
- `parse_date_time` handles `DD Mon YYYY [HH:MM[:SS]]` (English and Romanian month abbreviations including `Noi` for November) and `DD/MM/YYYY[[ HH:MM[:SS]]` — always returns a naive `datetime` with no tzinfo.
- `extract_text_after_label` tries all matching nodes, skipping those with no container or empty content, rather than stopping at the first node found.
- `extract_ids_from_links` falls back to `group(0)` when the pattern has no capture group.

**`markdown.py`** — bidirectional conversion: `html_to_markdown` (scraping Hipocrate HTML into report text) and `markdown_to_html` (exposed via `POST /fhir/md2html`).
- `html_to_markdown`: decomposes icon-only `<i>` tags (no text content) so they don't produce stray `*` markers; replaces heading tags with a plain text node to preserve `#` prefix inside block containers.
- `markdown_to_html`: processes bold before italic using STX/ETX sentinels to avoid `*` interference; uses distinct sentinel tags for `<ul>` vs `<ol>` items to prevent double-wrapping.

### Error handling conventions

- `web_fhir_response(str)` — wraps the string in an `OperationOutcome` and returns **400** (missing required parameter). Do not pass strings for server-side failures; build an `OperationOutcome` directly with the right severity.
- `OperationOutcome` HTTP status mapping: `not-found` code → 404; `error`/`fatal` severity → 500; `warning` → 400; `information` → 200.
- `HipoClientDiagnosticReport` and `HipoClientCheckout` override `fetch_and_parse` to evict the cache when the result is empty (report not yet written / epicrisis not yet filled).
- Datetime comparisons in `parse_data` always use naive datetimes. If the caller supplies a TZ-aware string, strip `tzinfo` before comparing (`datetime.replace(tzinfo=None)`).
- `fetch_and_parse` (base class) logs the exception and includes the message in the returned `HipoData` error — never swallow exceptions silently.
- Region filter uses `request.get('regions', [])` — requests parsed from the no-parent-row path may not have a `regions` key.

### Frontend (`static/`)

Single-page app: `main.html` + `scripts.js` + `styles.css` + `marked.js`.

- All API calls use `/fhir/*` endpoints with Basic Auth in the `Authorization` header.
- `marked.js` renders markdown in the Epicrisis and Report tabs.
- Both the **Epicrisis** and **Report** tabs use the same `.markdown-content` CSS class and the same Copy Markdown button pattern. Raw markdown is stored in `element.dataset.markdown` after render; the clipboard button reads from there with an `execCommand` fallback for plain HTTP.
- The **Report** tab assembles a clinical document (patient header → discharge summaries → imaging studies) structured for LLM consumption. The **Epicrisis** tab renders all encounters with an epicrisis, sorted by most-recent discharge, as a single markdown document.
- When a patient search returns multiple results, a selection overlay is shown — never pick `entry[0]` silently.
- Analyses fetch failure is non-fatal: a warning toast is shown and the patient tab still loads.
- Parallel fetches are throttled by `limitedMap(arr, MAX_CONCURRENT_REQUESTS=5, asyncFn)`.
- All dates are normalised to `YYYY-MM-DD` (or `YYYY-MM-DD HH:MM` with time) via `formatDate()` / `formatDateWithTime()` regardless of how Hipocrate sends them. **Never call `new Date(hipocrate_string).toISOString()`** — Hipocrate sends non-ISO date strings that produce invalid `Date` objects and throw `RangeError`. Always pass raw strings through `formatDate()` / `formatDateWithTime()`, which have `isNaN` guards and try/catch.
- Recent searches are persisted in `localStorage`.
- All DOM elements are cached at startup in the `elements` object via `getElementById`. Never look up the same element inside a function that runs repeatedly.
- Analysis cards use a `MODALITY_INFO` map (radio/ct/irm/eco/rads) for per-modality icon and label. Card type is stored in `article.dataset.type` and read by `filterAnalyses` — do not detect type from `className`. Modality CSS is driven by per-type custom properties (`--modality-radio`, `--modality-ct`, etc.) with separate light/dark values to meet WCAG AA contrast.
- Dynamic HTML uses `<template>` elements in `main.html` and `cloneNode(true)` + `textContent`/`className` in JS. Do not use `innerHTML` with interpolated strings for new elements.
- Theme cycles `auto → light → dark → auto` via `toggleTheme()`; `localStorage` key is `theme`.

### Dual API surface

Every resource type has two route families:
- `/api/<resource>` — returns `HipoData` as plain JSON (internal/debug use)
- `/fhir/<Resource>` — returns FHIR R4 JSON

The `?debug=page` query parameter on any `/api/*` endpoint returns the raw Hipocrate HTML for debugging scrapers.

### CSS design system

All colours, spacing, radii, and shadows use CSS custom properties defined in `:root` and `[data-theme="dark"]`. Key rules:
- Always use `var(--radius-sm/md/lg/full)` — `var(--radius)` is not defined.
- Always use `var(--font-size-xs/sm/base/lg/2xl/3xl/5xl)` and `var(--font-weight-normal/medium/semibold/bold)` — no hardcoded values.
- Header-specific button and badge styles are scoped to `.header .btn-icon` / `.header .badge` to avoid overriding general component styles.
- `--header-primary` / `--header-secondary` are separate from `--primary` / `--secondary` so the header gradient can use darker shades in dark mode without affecting the rest of the UI.
- Modality colors (`--modality-*`) have distinct light and dark values — the light values are darkened to meet WCAG AA 4.5:1 against white; the dark values are lighter for dark backgrounds.
