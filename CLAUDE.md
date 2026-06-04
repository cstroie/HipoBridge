# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the server

```bash
export HYP_USER=<username> HYP_PASS=<password>
python hipobridge.py
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

Tests require the server to be running on `http://localhost:44660` and credentials in `HYP_USER`/`HYP_PASS`.

```bash
python runtests.py               # all tests
python runtests.py extractors    # one group (no server needed)
python runtests.py markdown      # one group (no server needed)
```

Groups that don't hit the network: `extractors`, `markdown`, `hipodata`.  
Groups that need a live server: `root`, `auth`, `patients`, `analyses`, `reports`, `checkout`, `cnp`.

## Architecture

HippoBridge is a **scraping proxy**: it has no database. Every request authenticates against Hipocrate, scrapes HTML, and returns structured JSON or FHIR R4 resources.

### Request flow

```
HTTP client
  → hipobridge.py   (aiohttp routes + auth decorator)
  → HipoClient*     (fetches Hipocrate HTML, parses it)
  → fhir.py         (converts HipoData → FHIR resource)
  → web_fhir_response / web_json_response
```

### Key modules

**`hipobridge.py`** — entry point. Defines all routes and two response helpers:
- `web_json_response` — raw internal API (`/api/*`)
- `web_fhir_response` — FHIR-typed responses (`/fhir/*`); handles `OperationOutcome` on errors.
- `@require_auth` decorator extracts Basic Auth credentials and attaches them to `request.auth_credentials`.

**`hipoclient.py`** — the heaviest file (~3200 lines). One base class + six specialised subclasses, one per Hipocrate resource type:

| Class | Resource |
|---|---|
| `HipoClient` | Base: session management, fetch, cache, redirect following |
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

`UserSessionManager` (singleton `user_session_manager`) keeps one `aiohttp.ClientSession` per username to reuse cookies. Sessions are closed on app shutdown via `on_cleanup`.

`URLCache` (inner class, also standalone in `urlcache.py`) is an LRU cache with per-entry TTL used to avoid re-fetching the same Hipocrate URLs within a request burst.

**`fhir.py`** — FHIR R4 resource model. `Resource(MutableMapping)` is the base; all FHIR types subclass it. Resources serialize via `to_dict()`. `OperationOutcome.from_error()` is the standard way to return errors through the FHIR path.

**`hipodata.py`** — `HipoData(dict)` is a typed dict wrapper passed between the scraper and the FHIR converter. Keeps parsed field names consistent.

**`extractors.py`** — stateless HTML-parsing helpers used by `HipoClient` subclasses: `extract_text_after_label`, `extract_tabular_data`, `extract_id_from_link`, `parse_cnp`, `parse_date_time`, etc.

**`markdown.py`** — bidirectional conversion: `html_to_markdown` (used when scraping Hipocrate HTML into report text) and `markdown_to_html` (exposed via `POST /fhir/md2html`).

### Frontend (`static/`)

Single-page app in `static/main.html` + `static/scripts.js` + `static/styles.css`.

- All API calls go to `/fhir/*` endpoints using Basic Auth passed in the `Authorization` header.
- `marked.js` renders markdown in the Report tab.
- The Report tab assembles a clinical markdown document (patient → discharge summaries → imaging studies) intended to be copied and passed to an LLM for radiology insight summarisation. The raw markdown is stored in `patientReportMarkdown.dataset.markdown` after render; the Copy Markdown button reads from there.
- Concurrency for parallel fetches is throttled by `limitedMap(arr, MAX_CONCURRENT_REQUESTS, asyncFn)`.
- Recent searches are persisted in `localStorage`.

### Dual API surface

Every resource type has two route families:
- `/api/<resource>` — returns `HipoData` as plain JSON (internal/debug use)
- `/fhir/<Resource>` — returns FHIR R4 JSON

The `?debug=page` query parameter on any `/api/*` endpoint returns the raw Hipocrate HTML for debugging scrapers.
