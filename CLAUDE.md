# CLAUDE.md

## Server restarts

**Never restart the server yourself.** Tell the user when a restart is needed and wait for them to do it.

## Running the server

```bash
export HYP_USER=<username> HYP_PASS=<password>
python3 hipobridge.py
```

Test credentials are in `worklist.cfg` (`username` / `password` fields under `[worklist]`). Server runs on `http://127.0.0.1:44660`.

Default: `http://0.0.0.0:44660`. Override with `local.cfg` (not tracked by git):

```ini
[server]
port = 8080
[hipocrate]
service_url = http://192.168.3.230/hipocrate
```

CLI: `--port`, `--host`, `--service-url`, `--log-level DEBUG|INFO|WARNING|ERROR`, `--no-disk-cache`, `--no-worklist`.

## Running tests

```bash
python3 runtests.py               # all tests
python3 runtests.py extractors    # no server needed (also: markdown, hipodata)
```

## Architecture

HippoBridge is a **scraping proxy** — no database. Every request authenticates against Hipocrate, scrapes HTML, returns JSON or FHIR R4.

```
HTTP client → hipobridge.py (@require_auth) → HipoClient* (cache + semaphore) → fhir.py → response
```

### Client routing table

| Class | Route | Hipocrate URL |
|---|---|---|
| `HipoClientPatient` | `/api/patient/{id}` | `/Pacient/edit.asp?id={id}` |
| `HipoClientPatientSearch` | `/api/patient?q=` | `/files/search.asp?what=PA` |
| `HipoClientServiceRequest` | `/api/request/{id}` | `/PARA/Printabile/buletinRecoltari.asp?id={id}` |
| `HipoClientServiceRequestSearch` | `/api/request?patient=` | `/Pacient/analysesEpisod.asp` |
| `HipoClientImagingStudy` | `/api/study/{id}` | `/PARA/Printabile/BuletinAnalize.asp?id={id}&type=3` |
| `HipoClientDiagnosticReport` | `/api/report/{id}` | `/PARA/Printabile/BuletinAnalize.asp?id={id}&type=1` |
| `HipoClientCheckout` | `/api/checkout/{id}` | `/gen_printabile/BiletExternare.asp?RelId={id}&RelName=CO` |
| `HipoClientCheckin` | `/api/checkin/{id}`, `/fhir/Encounter/{id}?type=checkin` | `/files/checkin.asp?id={id}` |
| `HipoClientCheckup` | `/api/checkup/{id}`, `/fhir/Encounter/{id}?type=checkup` | `/files/checkup.asp?cuid={id}` |
| `HipoClientPresentation` | `/api/presentation/{id}`, `/fhir/Encounter/{id}?type=presentation` | `/gen_printabile/FisaPrezentare.asp?relname=PR&id={id}` |
| `HipoClientCerere` | `/api/request/{id}/patient`, `/fhir/ServiceRequest/{id}?type=cerere` | `/PARA/NOM/Listare/cerere.asp?id={id}` |
| `HipoClientReportWrite` | `POST /api/request/{id}/report` | `/PARA/NOM/Listare/cerere.asp` (POST) |
| `HipoClientReportValidate` | `POST /api/request/{id}/validate` | `/PARA/NOM/Listare/cerere.asp` (POST action=VDV) |
| `HipoClientCererePerform` | `POST /api/request/{id}/perform` | `/PARA/NOM/Listare/cerere.asp` (form replay, sets DataEfectuarii) |
| `HipoClientSchedule` | `/api/schedule`, `/fhir/Schedule` | `/PARA/NOM/Listare/?id=44&NrPePag=100` |
| `HipoClientObservationBundle` | `/fhir/Observation?patient=` | `/Pacient/analysesEpisod.asp` (parallel per domain) |
| `HipoClientWhoami` | `/api/whoami` | `Template/menu.asp` |

### Concurrency and caching (critical — Hipocrate is fragile)

- **Semaphore**: `_hipocrate_semaphore = asyncio.Semaphore(6)` — all outbound calls including login.
- **URLCache** (`urlcache.py`): LRU 500 entries, 30-min TTL. In-flight deduplication via `asyncio.Event` — `resolve_inflight()` **must** be called on every exit path including re-auth failures or waiters hang permanently.
- **UserSessionManager**: one `aiohttp.ClientSession` per username; per-user `asyncio.Lock` prevents concurrent login sequences.
- `login_if_needed(force=True)` skips the is-logged-in `main.asp` probe when session is known-expired.
- `DICOM_MODALITY` dict maps type codes to `(DICOM_code, human_display)` — never repeat the code string as display value.

### Key module gotchas

**`fhir.py`**:
- `Resource.__setitem__(key, None)` removes the key — never stores `None`.
- `OperationOutcome.from_error()` default code is `"processing"`. Pass explicit code for `"not-found"`, `"required"`, etc.
- `Encounter` uses R4 field names: `period`, `reasonCode`, `reasonReference`, `hospitalization` — not R5 names.

**`hipodata.py`**:
- `store()` strips strings, unwraps single-item lists, converts `datetime` → ISO, skips `None`. Dot-notation creates nested dicts.
- `get(key)` defaults to `None` — callers that need `""` must pass it explicitly.
- `set_success()` removes the `message` key rather than setting it to `""`.

**`extractors.py`**: `parse_date_time` handles Romanian month abbreviations including `Noi` for November.

**`markdown.py`**: `html_to_markdown` decomposes icon-only `<i>` tags; `markdown_to_html` uses STX/ETX sentinels for bold/italic ordering.

**`llm/`** (AI summary buttons — report/epicrisis/imaging/lab/pre_exam):
- Current production model: **`mistralai/ministral-3-3b` at Q4_K_M** (set in `local.cfg`'s `[provider:lmstudio]`, `default`/`medical` tiers). Chosen after an extensive benchmark survey — see `docs/llm_benchmark_2026-07-19.md` for the full methodology, per-kind fidelity scores, and model comparisons. Runner-up/fallback candidates: `medgemma-4b-it` (resident for xrayvision, so zero cold-load) and `google/gemma-3n-e4b`.
- **Do not "optimize" by dropping to a smaller quantization** — IQ4_XS and Q3_K_M were benchmarked and are *slower* on this model (more complex quant schemes cost more per-token dequant compute than they save in memory bandwidth at batch-size-1), with no quality upside. Stay on Q4_K_M.
- Prompts live in `llm/prompts/<kind>.md`, not hardcoded in `prompts.py` — edit the `.md` file to tune a prompt, no code change needed.
- `has_meaningful_content()` (`llm/prompts.py`) gates every call — never hand the model near-empty input; a small model will confidently fabricate an entire scenario (including demographics) rather than say there's nothing to summarize.
- `DATE_AWARE_KINDS`/`STREAMING_KINDS` (`llm/prompts.py`) are deliberately separate constants even though currently identical sets — one is about date context, the other about transport.
- The 4096-token context ceiling is real: an oversized input makes LM Studio return an SSE `event: error` line with no `choices` key, not a normal completion — `ServerBackend.chat_stream()`/`chat()` must check for `chunk.get("error")` explicitly or the failure is silently swallowed.

### Entry point conventions

- Log level: `LOG_LEVEL` env var or `--log-level`. Never hardcode `DEBUG`.
- Config loads in `init_app()`, not at import time.
- File paths: `os.path.join(os.path.dirname(__file__), ...)`.
- Credentials: `request['auth_credentials']` (aiohttp dict-style), not a plain attribute.
- `web_fhir_response(str)` → 400 OperationOutcome. Don't pass strings for server-side failures.
- `web_json_response`: `status="success"` → 200; "not found" in message → 404; other errors → 500.

### Error handling

- `OperationOutcome` HTTP status: `not-found` → 404; `error`/`fatal` severity → 500; `warning` → 400.
- `HipoClientDiagnosticReport` and `HipoClientCheckout` evict cache on empty result.
- Datetime comparisons use naive datetimes — strip `tzinfo` if caller passes TZ-aware strings.
- Never swallow exceptions in `fetch_and_parse` — log and include in returned `HipoData`.

### Scraper-specific gotchas

**Whoami**: Evicts the shared cache URL before and after each fetch (same URL for all users, user-specific content).

**Security**: `/gen_administrare/listare/cont.asp?id={user.id}&ses=1` echoes the user's password in plaintext (`strParola`) — do not scrape or expose this page.

**Cerere**: `cerere.asp` renders only the selected `<option>` with no `selected=` attribute — `_select_text()` takes the first `<option>` text.

**Schedule**:
- `html.parser` does not inject `<tbody>` — iterate `table.find_all('tr')` directly.
- Lab IDs are hardcoded (CT=26, US=28, MRI=32, X-Ray=49, IR=35, Fluoro=50) — do not guess.
- `_lab_to_modality`: check `radioscopii` before `radiografie` or combined labels resolve wrong.
- Ward filtering is Python-side (`?section_name=`); lab and patient-text filters are native Hipocrate URL params.

**DiagnosticReport / ObservationBundle**: `_parse_observation_value` is shared. Frontend detects lab entries by presence of `reference` key in `presentedForm`, not by `type="lab"` — immunology is typed `"other"` but still has `reference`.

**worklist.py**: Check `parse_cnp()` result via `parsed.get('valid')`, not `parsed.get('status')`. `wards` (not `sections`) key for ward filtering. `resolve_inflight()` must be called from `WorklistRefresher` exit paths too.

**Encounter route**: `?type=checkout|checkin|presentation` skips to right scraper. Without hint: tries all three in sequence (noisy logs). Frontend always passes `?type=`.

**Radiology report workflow** (cerere.asp write path):
- Access controlled by `_ALLOWED_RADIOLOGISTS` — a set of usernames from `[radiology] allowed_radiologists` in config. All three write endpoints (perform/report/validate) return 403 for non-members. `GET /api/whoami` returns `can_write_reports: true` when the authenticated user is in this set.
- **Perform**: `HipoClientCererePerform` GETs cerere.asp, extracts all form fields (skipping submit/button/image/reset; only checked checkboxes/radios), then POSTs back with `DataEfectuarii` overridden and `hdnAction=S`. JS validation in the browser blocks empty `DataEfectuarii`, but the server accepts it without `strSituatieNeincadrabila`/`Justificare`. Evicts cerere.asp and BuletinAnalize caches after POST.
- **Write**: POSTs report HTML to cerere.asp. Frontend converts textarea markdown to HTML via `marked.parse()` before posting.
- **Validate**: POSTs `action=VDV` to cerere.asp. Evicts both BuletinAnalize and cerere.asp caches.
- `performed_at` comes from `DataEfectuarii` input on cerere.asp. If blank (old exam done via Hipocrate UI), frontend also treats `allValidated` as implicit performed to suppress the Perform button.

**worklist.py** dedup/sort: After `_fetch_schedule`, entries are deduplicated by `request_id` (first occurrence wins) and sorted numerically by `request_id` before enrichment.

### Frontend (`static/`)

SPA: `main.html` + `scripts.js` + `styles.css` + `marked.js`. All assets self-hosted — no external requests.

**Critical rules:**
- **Never** `new Date(hipocrate_string)` — non-ISO strings produce `RangeError`. Always use `formatDate()` / `formatDateWithTime()`.
- **`calculateAge`** uses string splitting on `YYYY-MM-DD` — never `new Date(birthDate)`.
- **No `innerHTML`** with interpolated strings — use `<template>` + `cloneNode(true)` + `textContent`.
- **No `id` attributes inside `<template>`** — duplicated on every clone.
- Card type is in `article.dataset.type`, read by `filterAnalyses` — don't detect from `className`.
- Lab filter chip (`data-filter="lab"`) requires matching `<option value="lab">` in `#analysesFilter` or it silently no-ops.
- `SPARSE_THRESHOLD = 100` chars — checkin block is sparse if shorter, shows Last Admission stacked below.
- Multiple patient search results must show selection overlay — never silently pick `entry[0]`.
- Imaging history is always unfiltered; lab requests are limited to within 90 days of most recent result.
- `presentedForm` with `reference` key = lab entry regardless of `type` field.
- `.fas` rules need both `font-family` and `font-weight: 900` or icons are invisible.
- Nav uses `aria-current="page"` on `<li>`, not `role="tablist"` / `role="tab"` / `aria-selected`.
- All DOM elements cached at startup in `elements` — never query inside repeated functions.
- `whoamiReady` is a Promise that resolves after `fetchWhoami()` completes. Gate any UI that needs `canWriteReports` on `await whoamiReady`. After login, reassign `whoamiReady = fetchWhoami().catch(() => {})` so the flag is re-evaluated with the new credentials.
- `localDateStr(d?)` returns a `YYYY-MM-DD` string using local date methods — never `toISOString()` for date-only values (UTC lag).
- Report action buttons follow a 4-state machine per card: (1) not performed → Perform button only; (2) performed, no report → Edit Report; (3) performed + report → Edit Report + validate toggle; (4) performed + all validated → validate toggle only. Reset both buttons to `hidden` at the top of each `fetchAndFillReport` pass before re-evaluating state.
- New icon glyphs must be added to `static/fontawesome.css` — the file is a curated subset, not the full FA bundle. Check before using any `fa-*` class.

### CSS design system

- `var(--radius-sm/md/lg/full)` — `var(--radius)` is **not defined**.
- `var(--font-size-xs/sm/base/lg/2xl/3xl/5xl)` / `var(--font-weight-normal/medium/semibold/bold)`.
- `var(--spacing-xs/sm/md/lg/xl/2xl)` — no hardcoded `px` or `rem`.
- `--header-height: 72px` for sticky nav `top` offset.
- Modality colours: `--mod-xr`, `--mod-ct`, `--mod-mr`, `--mod-us`, `--mod-fl` (not `--modality-*`).

### Dual API surface

- `/api/<resource>` → `HipoData` plain JSON; `?debug=page` returns raw Hipocrate HTML.
- `/fhir/<Resource>` → FHIR R4 JSON.
