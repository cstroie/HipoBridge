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

**`hipoclient.py`** — the core scraping layer. One base class + eleven specialised subclasses:

| Class | Route | Hipocrate URL |
|---|---|---|
| `HipoClient` | — | Base: session management, fetch, cache, semaphore, auth |
| `HipoClientPatient` | `/api/patient/{id}` | `/Pacient/edit.asp?id={id}` |
| `HipoClientPatientSearch` | `/api/patient?q=` | `/files/search.asp?what=PA` |
| `HipoClientServiceRequest` | `/api/request/{id}` | `/PARA/Printabile/buletinRecoltari.asp?id={id}` |
| `HipoClientServiceRequestSearch` | `/api/request?patient=` | `/Pacient/analysesEpisod.asp` (parallel per domain) |
| `HipoClientImagingStudy` | `/api/study/{id}` | `/PARA/Printabile/BuletinAnalize.asp?id={id}&type=2` |
| `HipoClientDiagnosticReport` | `/api/report/{id}` | `/PARA/Printabile/BuletinAnalize.asp?id={id}&type=1` |
| `HipoClientCheckout` | `/api/checkout/{id}` | `/gen_printabile/BiletExternare.asp?RelId={id}&RelName=CO` |
| `HipoClientCheckin` | `/api/checkin/{id}` | `/files/checkin.asp?id={id}` |
| `HipoClientCheckup` | `/api/checkup/{id}` | `/files/checkup.asp?cuid={id}` |
| `HipoClientCerere` | `/api/request/{id}/patient` | `/PARA/NOM/Listare/cerere.asp?id={id}` |
| `HipoClientSchedule` | `/api/schedule`, `/fhir/Schedule` | `/PARA/NOM/Listare/?id=44&NrPePag=100` |

Every subclass (except `HipoClientCheckin` / `HipoClientCheckup` which are raw-JSON only) implements three methods:
- `fetch_and_parse(**kwargs)` → `HipoData` (raw dict)
- `fhir_response(parsed_data)` → FHIR resource object
- `fetch_respond_fhir(**kwargs)` → calls both, returns FHIR resource directly

`HipoClientCheckin` and `HipoClientCheckup` implement only `fetch_and_parse()`; they return `HipoData` via `/api/*` routes with no FHIR equivalent yet.

`HipoClientCerere` implements only `fetch_and_parse()`; it extracts `patient.id` from a `Pacient/edit.asp?id=` link in the request edit page. Used by the Schedule frontend to resolve a precise patient ID before triggering a search.

`HipoClientSchedule` overrides `fetch_and_parse` (URL is built from `?start_date=` / `?end_date=` query params, not an `{id}` path segment) and implements all three methods; the FHIR response is a `searchset` Bundle of `ServiceRequest` resources.

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

### Entry point (`hipobridge.py`) conventions

- **Log level** is controlled by the `LOG_LEVEL` environment variable (default `INFO`). Set `LOG_LEVEL=DEBUG` for development. Never hardcode `DEBUG` in the source.
- **Config loading** happens inside `init_app()`, not at module-import time. Module-level globals (`SERVICE_URL`, `_PORT`, `_HOST`) hold safe defaults and are overwritten by `init_app()` before any route is served.
- **All file paths** (`spec.json`, `static/`) are constructed with `os.path.join(os.path.dirname(__file__), ...)` so the server works regardless of the current working directory.
- **Request credentials** are stored as `request['auth_credentials']` (aiohttp dict-style storage), not as a plain attribute. Read them the same way in `HipoClient.__init__`.
- **`web_fhir_response`** sets `Content-Type: application/fhir+json` on every response (required by FHIR R4). Strings are wrapped in an `OperationOutcome` and returned as 400.
- **`web_json_response`** maps `status="success"` → 200, `status="error"` with "not found" in the message → 404, other errors → 500.

### Error handling conventions

- `web_fhir_response(str)` — wraps the string in an `OperationOutcome` and returns **400** (missing required parameter). Do not pass strings for server-side failures; build an `OperationOutcome` directly with the right severity.
- `OperationOutcome` HTTP status mapping: `not-found` code → 404; `error`/`fatal` severity → 500; `warning` → 400; `information` → 200.
- `HipoClientDiagnosticReport` and `HipoClientCheckout` override `fetch_and_parse` to evict the cache when the result is empty (report not yet written / epicrisis not yet filled).
- Datetime comparisons in `parse_data` always use naive datetimes. If the caller supplies a TZ-aware string, strip `tzinfo` before comparing (`datetime.replace(tzinfo=None)`).
- `fetch_and_parse` (base class) logs the exception and includes the message in the returned `HipoData` error — never swallow exceptions silently.
- Region filter uses `request.get('regions', [])` — requests parsed from the no-parent-row path may not have a `regions` key.

### Checkout (`HipoClientCheckout`) field notes

Extracts from `BiletExternare.asp`: patient identity, insurance (`patient.insurance_house`, `patient.insurance_category`, `patient.insurance_number`), address, phone, FO number (`checkout.fo_number`), urgency flag (`checkout.is_urgent`), primary and secondary diagnoses (ICD-10 split via `(?<=[a-zA-Z])(?=[A-Z]\d{2}\.)`), recommended treatment (`checkout.treatment`). FHIR output: insurance as `extension[]`, emergency as `priority`, secondary diagnoses as additional `Condition`-coded entries, treatment in `note[]`.

### Checkin (`HipoClientCheckin`) field notes

Page: `/files/checkin.asp?id={id}`. Expected title text: `FISA INTERNARE`. Extracts:
- `patient.name`, `patient.cnp` — from "Pacient [ NAME ] CNP X" pattern
- `checkin.presentation_id/date/urgency/section` — from presentation row
- `checkin.diagnosis_type` — radio label stripped of trailing instrument info
- `checkin.diagnosis`, `checkin.drg_diagnosis`, `checkin.diagnosis_72h`
- `checkin.secondary_diagnoses` — list, same ICD-10 split as checkout
- `checkin.transfers` — list of ward movements (7-cell rows; header rows with `Nr.Crt.` / `Cod cerere` / `Sectie` as first/second cell are excluded)
- `checkin.exam_general`, `checkin.exam_local`

No FHIR response implemented yet.

### Checkup (`HipoClientCheckup`) field notes

Page: `/files/checkup.asp?cuid={id}`. Expected title text: `Consult`. Extracts:
- `patient.name`, `patient.cnp`
- `checkup.presentation_date/urgency/section`
- `checkup.admission_id/date/section/medic` — linked inpatient admission if present
- `checkup.icd10`, `checkup.icd10_text`
- `checkup.initial_diagnosis`, `checkup.final_diagnosis`, `checkup.referral_diagnosis`
- `checkup.discharge_status`
- `checkup.exam_general`, `checkup.exam_local`

No FHIR response implemented yet.

### Cerere (`HipoClientCerere`) field notes

Page: `/PARA/NOM/Listare/cerere.asp?id={id}` — the request edit form. Extracts:
- `patient.id` — from the first `Pacient/edit.asp?id=(\d+)` link (case-insensitive)

Returns an error if no such link is found. Used exclusively by the Schedule tab to resolve a numeric patient ID before triggering a patient search; the frontend falls back to name search if this fails.

### Schedule (`HipoClientSchedule`) field notes

Page: `/PARA/NOM/Listare/?id=44&NrPePag=100` with date filter params `LR_requesteddateSD` / `LR_requesteddateED` (format `DD/MM/YYYY`; defaults to today). Page title: `Listare Cereri laborator`. Parses the `tbl_listare` table — one entry per `<tr class="class_0|class_1">` row. Does **not** rely on `<tbody>` (html.parser does not inject it); iterates `table.find_all('tr')` directly and takes `detail_rows[-1]` to skip the inner header row:
- `patient_name` — plain text in first `td.tdn`
- `request_code` — link text (e.g. `ES9686`) from second `td.tdn`
- `request_id` — numeric ID from the same link's `href`
- `date_time`, `status`, `payment_type`, `priority`, `section`, `requested_by`, `laboratory` — from the last `<tr>` of the nested `div.div_detalii` table (7 cells)

`date_time` is parsed via `parse_date_time` and normalised to `YYYY-MM-DD HH:MM` at scrape time (Hipocrate emits `DD/MM/YYYY HH:MM`).

FHIR output (`/fhir/Schedule?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`): `searchset` Bundle of `ServiceRequest` resources. Both params default to today if omitted; `?date=` is accepted as a backwards-compatible alias for `start_date`. Optional filter params applied in `fhir_response` before building the Bundle: `?patient=` (case-insensitive substring match on `patient_name`), `?modality=` (exact slug match via `_lab_to_modality`), `?section=` (exact match). `total` in the Bundle reflects the filtered count. Pass `?refresh=1` to evict the URL from the LRU cache before fetching (used by the Refresh button, which sends all current filter values alongside). Status mapping: `Cerere netrimisa` → `draft`; `Trimisa in laborator` / `Primita in laborator` → `active`; `Fara analize` → `on-hold`. Priority: `Normala` → `routine`, anything else → `urgent`. `request_code` → `identifier[0].value`; `section` → `note[0].text`; modality slug → `category[0].coding[0].code`.

Modality mapping (`_lab_to_modality`): `ecografie` → `eco`; `radioscopii` → `fluoro`; `radiografie` → `radio`; `tomografie` / `computerizata` / `computer tomograf` / standalone `ct` → `ct`; `imagistica` / `rezonanta` → `irm`; `laborator` → `lab`. Order matters — `radioscopii` is checked before `radiografie` so combined labels resolve to `fluoro`.

`fetch_and_parse` and `debug_page` are overridden (URL assembled from `?start_date=` / `?end_date=` query params, not an `{id}` path segment). `force=True` kwarg evicts the cache entry before the fetch.

### Frontend (`static/`)

Single-page app: `main.html` + `scripts.js` + `styles.css` + `marked.js`.

- All API calls use `/fhir/*` endpoints with Basic Auth in the `Authorization` header.
- `marked.js` renders markdown in the Epicrisis and Report tabs.
- Both the **Epicrisis** and **Report** tabs use the same `.markdown-content` CSS class and the same Copy Markdown button pattern. Raw markdown is stored in `element.dataset.markdown` after render; the clipboard button reads from there with an `execCommand` fallback for plain HTTP.
- The **Report** tab assembles a clinical document (patient header → discharge summaries → imaging studies) structured for LLM consumption. The **Epicrisis** tab renders all encounters with an epicrisis, sorted by most-recent discharge, as a single markdown document.
- When a patient search returns multiple results, a selection overlay is shown — never pick `entry[0]` silently. The overlay has `role="dialog"`, `aria-modal="true"`, an Escape-key handler, and a focus trap.
- Analyses fetch failure is non-fatal: a warning toast is shown and the patient tab still loads.
- Parallel fetches are throttled by `limitedMap(arr, MAX_CONCURRENT_REQUESTS=5, asyncFn)`.
- The in-memory `cache` (encounters + reports) is bounded to `CACHE_MAX=100` entries per store with oldest-first eviction via `cachePut()`.
- All dates are normalised to `YYYY-MM-DD` (or `YYYY-MM-DD HH:MM` with time) via `formatDate()` / `formatDateWithTime()` regardless of how Hipocrate sends them. **Never call `new Date(hipocrate_string).toISOString()`** — Hipocrate sends non-ISO date strings that produce invalid `Date` objects and throw `RangeError`. Always pass raw strings through `formatDate()` / `formatDateWithTime()`, which have `isNaN` guards and try/catch. **`calculateAge` uses string splitting on `YYYY-MM-DD` to avoid UTC midnight offset** — never `new Date(birthDate)` for age calculation.
- Recent searches are persisted in `localStorage`.
- All DOM elements are cached at startup in the `elements` object via `getElementById`. Never look up the same element inside a function that runs repeatedly.
- Analysis cards use a `MODALITY_INFO` map (radio/ct/irm/eco/rads) for per-modality icon and label. Card type is stored in `article.dataset.type` and read by `filterAnalyses` — do not detect type from `className`. Modality CSS is driven by per-type custom properties (`--modality-radio`, `--modality-ct`, etc.) with separate light/dark values to meet WCAG AA contrast.
- Dynamic HTML uses `<template>` elements in `main.html` and `cloneNode(true)` + `textContent`/`className` in JS. Do not use `innerHTML` with interpolated strings for new elements. Do not put `id` attributes inside `<template>` — they are duplicated on every clone.
- Theme cycles `auto → light → dark → auto` via `toggleTheme()`; `localStorage` key is `theme`.
- The **Schedule** tab is always visible (not gated on patient search). It fetches `/fhir/Schedule?start_date=…&end_date=…` on first visit and whenever the date inputs change. The date range defaults to yesterday–today. Filters: patient name (text input, partial match), modality (static dropdown), section (populated dynamically from loaded data) — all applied client-side by `renderSchedule()` with no re-fetch. The Refresh button re-fetches with `?refresh=1` (cache bust) **and** sends the current filter values as `?patient=`, `?modality=`, `?section=` so the server filters before building the Bundle. The Date/Time column shows time only for same-day ranges and full `YYYY-MM-DD HH:MM` for multi-day ranges. Patient name and request code cells are buttons that call `loadPatientFromRequest(requestId, patientName, el)`: fetches `/api/request/{id}/patient` to resolve the numeric patient ID, then submits the search form with that ID; falls back to name search if the fetch fails.

### HTML / accessibility conventions (`main.html`)

- There is exactly one `<h1>` per visible tab — the content heading (hero title, patient name, tab section title). The brand name uses `<p class="brand-name">`, not `<h1>`.
- Navigation uses `<nav aria-label="Main navigation">` with `aria-current="page"` on the active `<li>` — **not** `role="tablist"` / `role="tab"` / `aria-selected`, because the pattern is link-based and arrow-key tab widget semantics are not implemented.
- Tab panel containers are `<section role="tabpanel" aria-labelledby="...">`. Tab panel section headings carry the `id` referenced by `aria-labelledby`.
- Key-value patient info uses `<dl>`/`<dt>`/`<dd>` — not `<label>` (which is for form controls only).
- `<article>` is reserved for independently distributable content (analysis cards). Tab panel wrappers and markdown containers use `<div>` or `<section>`.
- The `<dialog>` in the imaging study modal template has `aria-labelledby` pointing to its `<h2>`.
- No Google Fonts external request — the body font stack already includes Inter as a system font fallback. Font Awesome is loaded from cdnjs with `crossorigin="anonymous" referrerpolicy="no-referrer"`.

### CSS design system

All colours, spacing, radii, and shadows use CSS custom properties defined in `:root` and `[data-theme="dark"]`. Key rules:
- Always use `var(--radius-sm/md/lg/full)` — `var(--radius)` is not defined.
- Always use `var(--font-size-xs/sm/base/lg/2xl/3xl/5xl)` and `var(--font-weight-normal/medium/semibold/bold)` — no hardcoded values.
- Always use `var(--spacing-xs/sm/md/lg/xl/2xl)` for padding/gap/margin — no hardcoded `px` or `rem` values.
- `--header-height: 72px` is defined in `:root`; use it for the sticky nav `top` offset.
- Header brand uses `.brand-name` (not `h1`) — styled by `.brand-name` selector, not `brand-info h1`.
- Header-specific button and badge styles are scoped to `.header .btn-icon` / `.header .badge` to avoid overriding general component styles.
- `--header-primary` / `--header-secondary` are separate from `--primary` / `--secondary` so the header gradient can use darker shades in dark mode without affecting the rest of the UI.
- Modality colors (`--modality-*`) have distinct light and dark values — the light values are darkened to meet WCAG AA 4.5:1 against white; the dark values are lighter for dark backgrounds.
- `@media (prefers-reduced-motion: reduce)` disables all animations and hover transforms; the CSS spinner becomes a static indicator.

### Dual API surface

Every resource type has two route families:
- `/api/<resource>` — returns `HipoData` as plain JSON (internal/debug use)
- `/fhir/<Resource>` — returns FHIR R4 JSON

The `?debug=page` query parameter on any `/api/*` endpoint returns the raw Hipocrate HTML for debugging scrapers.

