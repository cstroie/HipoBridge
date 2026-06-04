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
- `fetch_repond_fhir(**kwargs)` → calls both, returns FHIR resource directly

**Concurrency and caching** (critical — Hipocrate is a fragile legacy server):
- `_hipocrate_semaphore = asyncio.Semaphore(6)` — global cap on concurrent outbound HTTP calls; all request paths including login go through this.
- `URLCache` (`urlcache.py`) — LRU cache, 500 entries, 30-minute TTL. In-flight deduplication via `asyncio.Event`: if two coroutines miss the cache for the same URL simultaneously, the second waits for the first's result rather than issuing a duplicate request.
- `UserSessionManager` — one `aiohttp.ClientSession` per username (cookie reuse). Includes a per-user `asyncio.Lock` so concurrent requests from the same user never trigger two simultaneous login sequences. Tracks `is_authenticated` state to skip redundant Hipocrate probes.
- `login_if_needed(force=True)` — skip the is-logged-in main.asp probe when the caller already knows the session is expired.

**`fhir.py`** — FHIR R4 resource model. `Resource(MutableMapping)` is the base; all FHIR types subclass it. Resources serialize via `to_dict()`. `OperationOutcome.from_error()` is the standard way to signal errors through the FHIR path.

**`hipodata.py`** — `HipoData(dict)` typed dict wrapper passed between the scraper and the FHIR converter. `store(key, value)` normalises values (strips strings, unwraps single-item lists, converts datetimes to ISO). Dot-notation keys (`"patient.id"`) create nested dicts automatically.

**`extractors.py`** — stateless HTML-parsing helpers: `extract_text_after_label`, `extract_tabular_data`, `extract_id_from_link`, `parse_cnp`, `parse_date_time`, etc.

**`markdown.py`** — bidirectional conversion: `html_to_markdown` (scraping Hipocrate HTML into report text) and `markdown_to_html` (exposed via `POST /fhir/md2html`).

### Frontend (`static/`)

Single-page app: `main.html` + `scripts.js` + `styles.css` + `marked.js`.

- All API calls use `/fhir/*` endpoints with Basic Auth in the `Authorization` header.
- `marked.js` renders markdown in the Epicrisis and Report tabs.
- Both the **Epicrisis** and **Report** tabs use the same `.markdown-content` CSS class and the same Copy Markdown button pattern. Raw markdown is stored in `element.dataset.markdown` after render; the clipboard button reads from there with an `execCommand` fallback for plain HTTP.
- The **Report** tab assembles a clinical document (patient header → discharge summaries → imaging studies) structured for LLM consumption. The Epicrisis tab renders a single encounter as a markdown doc (diagnosis heading + metadata line + full text).
- Parallel fetches are throttled by `limitedMap(arr, MAX_CONCURRENT_REQUESTS=5, asyncFn)`.
- All dates are normalised to `YYYY-MM-DD` (or `YYYY-MM-DD HH:MM` with time) via `formatDate()` / `formatDateWithTime()` regardless of how Hipocrate sends them. **Never call `new Date(hipocrate_string).toISOString()`** — Hipocrate sends non-ISO date strings that produce invalid `Date` objects and throw `RangeError`. Always pass raw strings through `formatDate()` / `formatDateWithTime()`, which have `isNaN` guards and try/catch.
- Recent searches are persisted in `localStorage`.
- All DOM elements are cached at startup in the `elements` object via `getElementById`. Never look up the same element inside a function that runs repeatedly.
- Analysis cards use a `MODALITY_INFO` map (radio/ct/irm/eco/rads) for per-modality icon and label. Modality CSS is driven by per-type custom properties (`--modality-radio`, `--modality-ct`, etc.) with separate light/dark values to meet WCAG AA contrast.

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
