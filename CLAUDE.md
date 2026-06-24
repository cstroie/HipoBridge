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

**`hipoclient.py`** — the core scraping layer. One base class + fifteen specialised subclasses:

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
| `HipoClientPresentation` | `/api/presentation/{id}`, `/fhir/Encounter/{id}?type=presentation` | `/files/presentation.asp?id={id}` |
| `HipoClientCerere` | `/api/request/{id}/patient`, `/fhir/ServiceRequest/{id}?type=cerere` | `/PARA/NOM/Listare/cerere.asp?id={id}` |
| `HipoClientSchedule` | `/api/schedule`, `/fhir/Schedule` | `/PARA/NOM/Listare/?id=44&NrPePag=100` |
| `HipoClientObservationBundle` | `/fhir/Observation?patient=` | `/Pacient/analysesEpisod.asp` (parallel per lab domain) |
| `HipoClientWhoami` | `/api/whoami` | `Template/menu.asp` (CONTUL MEU block) |

Every subclass (except `HipoClientCheckin` / `HipoClientCheckup` which are raw-JSON only) implements three methods:
- `fetch_and_parse(**kwargs)` → `HipoData` (raw dict)
- `fhir_response(parsed_data)` → FHIR resource object
- `fetch_respond_fhir(**kwargs)` → calls both, returns FHIR resource directly

`HipoClientCheckin` and `HipoClientCheckup` implement only `fetch_and_parse()`; they return `HipoData` via `/api/*` routes with no FHIR equivalent yet.

`HipoClientCerere` implements all three methods; it parses the full request edit form (patient name/CNP, physician, ward, priority, diagnosis, clinical indication, exam list). See the Cerere field notes section for details.

`HipoClientSchedule` overrides `fetch_and_parse` and `debug_page` (URL built from `?start_date=` / `?end_date=` / `?lab_id=` / `?patient_text=` query params, not an `{id}` path segment) and implements all three methods; the FHIR response is a `searchset` Bundle of `ServiceRequest` resources. Section filtering is Python-side in `fhir_response`.

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
- `Observation` — added for lab analyte measurements: fields `status`, `code`, `subject`, `effectiveDateTime`, `valueQuantity`, `valueString`, `referenceRange`, `interpretation`, `basedOn`.

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

**`worklist.py`** — optional DICOM Modality Worklist (MWL) SCP. Runs in a daemon thread alongside the aiohttp server. Started by `init_app()` if `worklist.cfg` exists. See `WORKLIST.md` for full documentation.

Key constants:
- `_MODALITY_SLUG_TO_LAB_ID` — maps modality slugs (`ct`, `eco`, `irm`, `radio`, `rads`, `fluoro`) to Hipocrate `PARA_ID_Laborator` values. Do not guess these IDs.
- `_MODALITY_FETCH_DAYS` — days ahead to fetch per slug: 3 for X-Ray/US/Fluoro, 7 for CT/MRI. `_DEFAULT_FETCH_DAYS = 2` when no modality is specified.
- `_LAB_ID_FETCH_DAYS` — reverse of the above: `lab_id → days ahead`.
- `_MODALITY_CODE` — maps slugs to DICOM modality codes (`CT`, `US`, `MR`, `CR`, `RF`). LAB is absent — lab requests do not use the DICOM worklist.
- `_DICOM_CODE_TO_LAB_IDS` — reverse map: DICOM code → list of Hipocrate lab IDs (e.g. `RF → ['35', '50']` because RF covers both Interventional Radiology and Fluoroscopy). Used by `_lab_ids_for_profile()` to look up which Hipocrate labs to query for a given device modality.

Key classes:
- `WorklistCache` — per-modality slots: `Dict[lab_id → (datasets, raw, updated_at)]` under one `threading.Lock`. `update(lab_id, ...)` replaces a single slot; `snapshot(lab_id)` returns one slot; `snapshot_multi(lab_ids)` merges several slots (used for RF which spans two labs); `snapshot(None)` merges all (for unconfigured devices).
- `WorklistRefresher` — asyncio task. `refresh(lab_id)` fetches the schedule for one modality, enriches patient demographics via `HipoClientCerere` + `HipoClientPatient`, builds pydicom Datasets via `_build_datasets()`, updates the cache slot. `refresh_if_stale(lab_id, max_age_seconds)` throttles concurrent C-FIND triggers with a `threading.Lock`. No periodic background refresh — cache is warmed on-demand. Stores `_accession_prefix` (from `worklist.cfg [worklist] accession_prefix`); passes it to `_build_datasets`.
- `WorklistServer` — pynetdicom `AE`. `handle_find()` runs in pynetdicom's thread; bridges to the asyncio loop via `asyncio.run_coroutine_threadsafe`. Unknown AE titles → `0xA700` Failure (AE allowlist). `_matches_cfind()` applies PatientName (substring), PatientID (exact), AccessionNumber (exact), date range, and Modality filters from the C-FIND identifier. Each match is logged at DEBUG level (accession | patient | exam). Device profiles are hot-reloaded on each association: `_reload_profiles_if_changed()` compares `os.path.getmtime()` of `worklist.cfg` and re-parses only the device profile sections (port and AE title cannot change at runtime).

Dataset building: `_build_datasets(entry, patient_info, accession_prefix='') -> List[Dataset]` — one Dataset per exam. A single Hipocrate request with N exams from `cerere.asp` produces N Datasets sharing the same `AccessionNumber` (`{prefix}{request_id}`) and `StudyInstanceUID` (`1.2.840.99999999.1.{request_id}`), with `ScheduledProcedureStepID` suffixed (`request_id-1`, `request_id-2`). Single-exam requests produce one Dataset with no suffix. `PatientID` is the CNP; when DOB or sex are absent from the patient record, they are derived from the CNP via `parse_cnp()` (check `parsed.get('valid')`, not `parsed.get('status')`).

Name conversion: `_name_to_dicom(name)` converts Romanian name strings to DICOM PN (`Family^Given^Middle^Prefix`). Title prefixes (`DR`, `PROF`, `CONF`, `SL`, `S.L`, etc.) go into the fourth component; no trailing `^` when the fifth component is empty. `_split_glued_prefix(tok)` handles cases like `DR.POPESCU` where the prefix is glued to the family name.

Config: `worklist.cfg` (gitignored, contains credentials + device profiles) and `worklist.cfg.example` (tracked, template with full documentation). `start_worklist()` returns the `WorklistServer` instance or `None` if the server is disabled; `on_cleanup` calls `server.shutdown()` via `run_in_executor` to avoid blocking the event loop. Device `modality` accepts DICOM codes (`CT`, `MR`, `US`, `CR`, `RF`) as well as legacy slugs (`ct`, `irm`, `eco`, `radio`, `fluoro`, `rads`). `wards` (not `sections`) is a comma-separated list of substrings matched case-insensitively against the Hipocrate ward name.

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

### Buletin pages (`HipoClientImagingStudy` / `HipoClientDiagnosticReport`) shared header

`_parse_buletin_header` parses the common BuletinAnalize header (patient, request date, barcode, urgency, medic) **and the clinical indication**: the `<p class="NoteSubsol"><b>INFO SUPLIMENTAR:</b> …</p>` footer note → `request.clinical_comments`. Both FHIR converters emit it as `note[]` entry with `category[0].text = "clinical-indication"`; the frontend filters notes on that category to populate the analysis card's `request-meta` (Indication) and treats the rest as result notes.

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

### Whoami (`HipoClientWhoami`) field notes

Page: `Template/menu.asp` (sidebar menu iframe), CONTUL MEU / Informatii personale section. (`main.asp` is no longer scraped — its `div.clockSession` block was not reliably present.) Stores: `user.display_name` from the `<small>` under the `CONTUL MEU` `td.menu_caps` (`[ DR. STROIE COSTIN ]`, brackets and `&nbsp;` stripped), `user.id` — the real user ID, the full number from the `cont.asp?id=(\d+)` link (e.g. `421200000000744`), and `user.username` — the Basic Auth login name (the menu page does not repeat the account string anywhere parseable). Errors only if neither the CONTUL MEU block nor a `cont.asp?id=` link is found. **Cache safety:** the page is the same URL for every user but user-specific in content, so `fetch_and_parse` evicts the URL from the shared cache before and after the fetch. Raw-JSON only (`/api/whoami`); no FHIR equivalent. `POST /api/logout` closes the caller's Hipocrate session via `user_session_manager.close_user_session(username)` — it cannot clear the browser's Basic Auth credentials.

Future tip: `/gen_administrare/listare/cont.asp?id={user.id}&ses=1` ("Informatii personale") exposes employee details — `strIDAngajat`, name parts, CNP, parafa (`strParafa`), phone/email/address fields. **Do not scrape or expose it wholesale: the page echoes the user's current password in plaintext (`strParola`).**

### Presentation (`HipoClientPresentation`) field notes

Page: `/files/presentation.asp?id={id}`. Expected title text: `Fisa de Prezentare`. Extracts:
- `patient.name` — from `Pacient/edit.asp` header link text (brackets stripped)
- `patient.id` — from `hdnPacID` hidden input
- `patient.cnp` / `patient.gender` / `patient.date` / `patient.age` — from `strCNP` input or CNP table row
- `presentation.id`, `presentation.date`, `presentation.time`, `presentation.date_time` (combined)
- `presentation.registry` — registry number (`strRefID`)
- `presentation.checkin_id` — linked inpatient admission (`checkinID` input); present when visit led to hospitalisation
- `presentation.checkup_id` — linked consultation ID (`savedCUId`)
- `presentation.decision_code` — numeric decision code (`savedCUDecision`)
- `presentation.section` — ward/triage unit from `Garda:` row (e.g. `UPU`)
- `presentation.medic` — attending physician from `Medic:` label in same row
- `presentation.is_urgent` — from `Urgenta: DA` cell
- `presentation.reason` — from `EmergencyReason` select
- `presentation.transport_type` / `transport_number` / `transport_medic` — from `selTransportType`, `strTransportNumber`, `strTransportDoctor`
- `presentation.consult_type` — from `sCUType` select
- `presentation.decision` — discharge decision text from the consultations table row matching `checkup_id`

FHIR Encounter: class `EMER` for UPU/CPU/URGENTA/URGENTE sections, `AMB` otherwise. `partOf` references the linked checkin encounter when `checkin_id` is present. Transport details in nested `extension[]`. `reasonCode[0].text` = reason; `note[0]` = decision, `note[1]` = consult type. The FHIR Patient resource exposes presentation IDs in extension `presentation-ids`; the frontend passes `?type=presentation` to `/fhir/Encounter/{id}` to skip directly to this scraper.

### Cerere (`HipoClientCerere`) field notes

Page: `/PARA/NOM/Listare/cerere.asp?id={id}` — the request edit form. Extracts:
- `request.id` — from the `id` kwarg (URL path parameter)
- `patient.id` — from the first `Pacient/edit.asp?id=(\d+)` link; error if absent
- `patient.name` — from the `Pacient/edit.asp` link text (brackets stripped)
- `patient.cnp` — from `strCNP` input or "CNP" label; fallback: first 13-digit number in page text
- `patient.gender` / `patient.date` / `patient.age` — derived from CNP via `parse_cnp()` when valid
- `request.date_time` — from `strDataCerere` input or "Data cerere" label (ISO format after `parse_date_time`)
- `request.priority` — from `PARA_ID_Prioritate` select or "Prioritate" label
- `request.hospitalization_type` — from `PARA_ID_TipSpitalizare` select or "Tip internare" label
- `request.physician` — from `PARA_ID_Medic` select or `strMedic` input or "Medic" label
- `request.section` — from `PARA_ID_Sectie` select or "Sectie" label
- `request.diagnosis` — from `strDiagnostic` input or "Diagnostic" label
- `request.justification` — from `strJustificare` textarea or "Justificare" label
- `request.clinical_indication` — from `strInfoSuplimentar` textarea, "Informatii suplimentare" label, or `<p class="NoteSubsol">` INFO SUPLIMENTAR footer
- `exams` — list of ordered exam names (four patterns: `tr_class_generic_1` rows → numbered rows → checked checkboxes → checkbox labels)

Returns an error if `patient.id` is not found. All other fields are optional — absent from HipoData if not extractable. Selector patterns were designed from the Hipocrate form conventions; use `?debug=page` to inspect the raw HTML and tune if needed.

Routes:
- `GET /api/request/{id}/patient` — returns full `HipoData` JSON; supports `?debug=page`
- `GET /fhir/ServiceRequest/{id}?type=cerere` — returns FHIR `ServiceRequest`

FHIR mapping: `patient.id` → `subject.reference`; `patient.name` → `subject.display`; `request.date_time` → `authoredOn`; `request.priority` → `priority` (`urgent`/`routine`); `request.physician` → `requester.display`; `request.diagnosis` → `reason[0].display`; `request.hospitalization_type` → `category[0].text`; `exams` → `orderDetail[{text}]`; `request.section` → `note[0].text`; `request.clinical_indication` → `note[1].text`; `request.justification` → `note[2].text`.

Also used internally by `WorklistRefresher` to resolve `patient.id` and `exams` for DICOM MWL dataset building.

### Schedule (`HipoClientSchedule`) field notes

Page: `/PARA/NOM/Listare/?id=44&NrPePag=200` with date filter params `LR_requesteddateSD` / `LR_requesteddateED` (format `DD/MM/YYYY`; defaults to today). Page title: `Listare Cereri laborator`. Parses the `tbl_listare` table — one entry per `<tr class="class_0|class_1">` row. Does **not** rely on `<tbody>` (html.parser does not inject it); iterates `table.find_all('tr')` directly and takes `detail_rows[-1]` to skip the inner header row:
- `patient_name` — plain text in first `td.tdn`
- `request_code` — link text (e.g. `ES9686`) from second `td.tdn`
- `request_id` — numeric ID from the same link's `href`
- `date_time`, `status`, `payment_type`, `priority`, `section`, `requested_by`, `laboratory` — from the last `<tr>` of the nested `div.div_detalii` table (7 cells)

`date_time` is parsed via `parse_date_time` and normalised to `YYYY-MM-DD HH:MM` at scrape time (Hipocrate emits `DD/MM/YYYY HH:MM`).

**Filtering architecture** — two native Hipocrate URL params filter at source: `PARA_ID_Laborator` (lab numeric ID, passed as `?lab_id=`) and `PARA_TextCautare` + `PARA_ID_TipCautare=2` (patient free-text search, passed as `?patient_text=`). Ward filtering is Python-side in `fhir_response` via exact match on the `section` field (`?section_name=`). Hipocrate lab IDs (hardcoded): CT=26, Ultrasound=28, MRI=32, X-Ray=49, Interventional Radiology=35, Fluoroscopy=50. These IDs come from `/gen_lib/filtre_ajax_dropdown.asp?N=PARA_ID_Laborator&P1=44&…` — do not guess them. `PARA_Ordonare=2` is always passed for consistent sort order.

FHIR output (`/fhir/Schedule?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`): `searchset` Bundle of `ServiceRequest` resources. Both params default to today if omitted; `?date=` is accepted as a backwards-compatible alias for `start_date`. Filter params: `?lab_id=` (native Hipocrate), `?patient_text=` (native Hipocrate), `?section_name=` (Python-side exact match). `total` reflects the post-filter count. Pass `?refresh=1` to evict the URL from the LRU cache. Status mapping (FHIR R6 `ended` used for `Terminata`): `Cerere netrimisa` → `on-hold`; `Trimisa in laborator` / `Primita in laborator` → `draft`; `In lucru(NV)` → `active`; `Cerere completata` / `Cerere completata/partial validata` → `completed`; `Terminata` → `ended`; `Fara analize` → `entered-in-error`. Priority: `Normala` → `routine`, anything else → `urgent`. `request_code` → `identifier[0].value`; `section` → `note[0].text`; `payment_type` → `note[1].text`; modality slug → `category[0].coding[0].code`.

Modality mapping (`_lab_to_modality`): `ecografie` → `eco`; `radioscopii` → `fluoro`; `radiografie` → `radio`; `tomografie` / `computerizata` / `computer tomograf` / standalone `ct` → `ct`; `imagistica` / `rezonanta` → `irm`; `laborator` → `lab`. Order matters — `radioscopii` is checked before `radiografie` so combined labels resolve to `fluoro`.

`fetch_and_parse` and `debug_page` are overridden (URL assembled from query params, not an `{id}` path segment). `force=True` kwarg evicts the cache entry before the fetch.

### ObservationBundle (`HipoClientObservationBundle`) field notes

Route: `GET /fhir/Observation?patient={id}`. Aggregates lab analyte measurements from the most recent episode across all 15 lab domains for the Trends table.

`LAB_DOMAINS = [1, 2, 3, 5, 8, 9, 15, 19, 21, 22, 23, 24, 27, 39, 41]` — Hipocrate lab domain IDs (Bacteriologie, Biochimie, Hematologie, Coagulare, etc.). Fetches `analysesEpisod.asp?pacid={id}&strDomeniu={domain}&NrPePag=1` per domain (newest first; `NrPePag=1` = last episode only), then filters candidates to within ±1 day of the most recent date found across all domains. Each analyte row within those DiagnosticReports becomes one `Observation` resource.

`_parse_observation_value(result_text, reference_text)` → `(value, unit, low, high, flag)` — shared helper used by both `HipoClientObservationBundle` and `HipoClientDiagnosticReport`. Parses numeric value (handles `<`/`>` qualifiers and comma decimals), extracts unit from reference range text, computes H/L/N flag by comparing value against low/high bounds.

`HipoClientDiagnosticReport.fhir_response` enriches each `presentedForm` entry with `reference`, `section`, and `flag` fields (from `_parse_observation_value`) so the frontend can render lab results as grouped tables. Detection in the frontend: any `presentedForm` entry with a `reference` key is treated as a lab entry regardless of its `type` field — this handles immunology and other sections typed as `"other"` rather than `"lab"`.

### Encounter route (`/fhir/Encounter/{id}`) type hint

Accepts `?type=checkout|checkin|presentation` to skip directly to the right scraper. Without the hint: tries checkout → checkin → presentation in sequence (legacy fallback, produces noisy logs). The FHIR Patient resource exposes three separate ID lists as extensions (`checkout-ids`, `checkin-ids`, `presentation-ids`) derived from distinct href patterns on the patient page — the frontend always passes the correct `?type=` so sequential fallback is never triggered in normal operation.

### Frontend (`static/`)

Single-page app: `main.html` + `scripts.js` + `styles.css` + `marked.js`. All fonts (Space Grotesk, JetBrains Mono, Inter) and Font Awesome icons are self-hosted under `static/fonts/` — no external requests are made.

- All API calls use `/fhir/*` endpoints with Basic Auth in the `Authorization` header.
- **Auth flow**: credentials are stored in `sessionStorage` under `CRED_KEY`. On load, if no credentials are found, a JS login `<dialog id="loginDialog">` is shown. `apiFetch(url, options)` injects the `Authorization` header on every request and re-shows the login dialog on 401. The main page is served unconditionally (no `@require_auth` on the HTML route). Logout calls `clearCredentials()` then `showLoginDialog()`.
- `marked.js` renders markdown in the Epicrisis and Report tabs.
- Both the **Epicrisis** and **Report** tabs use the same Copy Markdown button pattern. Raw markdown is stored in `element.dataset.markdown`; the clipboard button reads from there with an `execCommand` fallback for plain HTTP.
- The **Report** tab assembles a clinical document structured for LLM consumption: patient header → Current Admission (active inpatient checkin) → Last Admission (most recent epicrisis) → Recent Imaging (up to 5 with text). The **Copy** button on the Report tab copies exactly what is rendered — not the full epicrisis history. The **Epicrisis** tab renders all encounters with an epicrisis, sorted by most-recent discharge, as a single markdown document with its own Copy button.
- **Report admission logic**: active inpatient → show **Current Admission** block (checkin fields). If checkin text is sparse (< 100 chars), also show **Last Admission** (most recent discharge epicrisis) stacked below. Outpatients → show **Last Admission** only. The threshold is `SPARSE_THRESHOLD = 100`.
- **Report imaging**: fetches up to 20 candidates, skips entries with no report text (e.g. in-progress investigations), renders up to 5 with text. `entries` and `reports` arrays are hoisted to outer scope so the markdown builder can reference them.
- **Analyses episode filter** (server-side): lab requests are limited to within 90 days of the most recent lab result (current episode). Imaging requests are **not** filtered — the full imaging history is always returned. Both are merged and sorted by date descending.
- When a patient search returns multiple results, a selection overlay is shown — never pick `entry[0]` silently. The overlay has `role="dialog"`, `aria-modal="true"`, an Escape-key handler, and a focus trap.
- Analyses fetch failure is non-fatal: a warning note is set on the analyses eyebrow element and the patient tab still loads.
- Parallel fetches are throttled by `limitedMap(arr, MAX_CONCURRENT_REQUESTS=5, asyncFn)`.
- The in-memory `cache` (encounters + reports) is bounded to `CACHE_MAX=100` entries per store with oldest-first eviction via `cachePut()`.
- All dates are normalised to `YYYY-MM-DD` (or `YYYY-MM-DD HH:MM` with time) via `formatDate()` / `formatDateWithTime()` regardless of how Hipocrate sends them. **Never call `new Date(hipocrate_string).toISOString()`** — Hipocrate sends non-ISO date strings that produce invalid `Date` objects and throw `RangeError`. Always pass raw strings through `formatDate()` / `formatDateWithTime()`, which have `isNaN` guards and try/catch. **`calculateAge` uses string splitting on `YYYY-MM-DD` to avoid UTC midnight offset** — never `new Date(birthDate)` for age calculation.
- Recent searches are persisted in `localStorage`.
- All DOM elements are cached at startup in the `elements` object via `getElementById`. Never look up the same element inside a function that runs repeatedly.
- Analysis cards use two maps: `MODALITY_INFO` (radio=X-Ray, ct=CT, irm=MRI, eco=Ultrasound, rads=Fluoroscopy, lab=Laboratory) for icon and label, and `MODALITY_AVATAR` for the coloured circle SVG icon and CSS class (cls: `mod-xr`, `mod-ct`, `mod-mr`, `mod-us`, `mod-fl`, `mod-lab`). Icons use an inline SVG sprite (`<symbol>` / `<use href="#id">`) embedded in `main.html`; `modAvatarHTML(slug)` returns the `<svg><use>` markup. Symbol IDs: `mod-radio` (radiology.svg), `mod-ct` (med/mri-pet.svg, viewBox `-11 -11 86 86` for visual padding), `mod-irm` (neurology.svg), `mod-eco` (sonography.svg), `mod-fluoro` (nephrology.svg), `mod-lab` (med/laboratory.svg), `mod-inpatient`, `mod-outpatient`. The `.mod-circle` has no background or border-radius — it is a plain sized container; colour is applied via `color: var(--mod-xx)` and SVG inherits via `currentColor`. Card type is stored in `article.dataset.type` and read by `filterAnalyses` — do not detect type from `className`. The analyses filter chip strip includes a **Lab** chip (`data-filter="lab"`); its value must exist as `<option value="lab">` in the hidden `#analysesFilter` select or the filter silently no-ops. Modality colours use CSS custom properties `--mod-xr`, `--mod-ct`, `--mod-mr`, `--mod-us`, `--mod-fl` with separate light/dark values. Cards with no report result receive `no-report` class (faded, dashed border) instead of showing placeholder text. Multi-series imaging studies render each result under a `<p class="series-result-title">` label drawn from `series[i].description`. Timeline modality icons are 64×64px.
- **Lab result rendering**: `buildLabTable(forms)` detects lab entries as any `presentedForm` with a `reference` field (set by the enriched backend — includes immunology/`type="other"` entries). Groups by `section`, renders as `<table class="lab-result-table">` with analyte name / value (`.lab-high` / `.lab-low` highlight) / reference columns and H/L badges. Used in both `fetchAndFillReport` (card inline preview) and `renderReportContent` (modal).
- **Lab trends**: `loadTrends(patientId)` fetches `/fhir/Observation?patient={id}` after patient loads; `renderTrends(observations)` groups by analyte, builds a date×analyte table with inline SVG sparklines. Non-fatal — a fetch failure shows a warning but does not block the patient tab. Trends section is in `#trendsSection` below the analyses grid.
- **Analyses episode filter**: see the "Analyses episode filter" bullet above in the Frontend section — lab-only cutoff, imaging unrestricted.
- **Hospitalization history colour-coding**: `li.dataset.type` is set to `"inpatient"` or `"outpatient"` on each history item. CSS attribute selectors colour the dot, card border, and badge: inpatient = amber (`--mod-ct`), outpatient = teal (`--mod-us`).
- **Page load**: all tab panels and the `<header class="app-bar">` start `hidden style="display:none"` in the HTML. `initApp()` calls `initializeTabs()` → `switchTab('schedule')` which removes `hidden` and sets `display:block` on the active panel, then reveals the header. `switchTab` always calls `removeAttribute('hidden')` before setting `display:block`.
- Dynamic HTML uses `<template>` elements in `main.html` and `cloneNode(true)` + `textContent`/`className` in JS. Do not use `innerHTML` with interpolated strings for new elements. Do not put `id` attributes inside `<template>` — they are duplicated on every clone.
- Theme cycles `auto → light → dark → auto` via `toggleTheme()`; `localStorage` key is `theme`.
- The **Schedule** tab is always visible (first in nav, default active tab on page load; not gated on patient search). It fetches `/fhir/Schedule?start_date=…&end_date=…` on first visit; date range defaults to yesterday–today. Every filter change triggers a new server request — no client-side filtering. Filters: **patient name** (text input — fires on Enter only, sends `?patient_text=`), **modality** (hardcoded `<select>` with Hipocrate IDs, sends `?lab_id=`), **ward** (dynamic `<select>` populated from the first unfiltered fetch result and kept in memory, sends `?section_name=`). The Refresh button re-fetches with `?refresh=1` to bypass cache. `renderSchedule()` renders `scheduleEntries` as-is with no local filtering. The Date/Time column shows time only for same-day ranges and full `YYYY-MM-DD HH:MM` for multi-day ranges. Clicking a patient name calls `loadPatientFromRequest(requestId, patientName, el)`: fetches `/api/request/{id}/patient` to resolve the numeric patient ID, then submits the search form with that ID; falls back to name search if the fetch fails. Clicking a request code opens `showRequestModal(requestId, requestCode, patientName, modality, triggerEl, requesterName)`, which fetches the exam report (`ImagingStudy` or `DiagnosticReport` based on modality) and renders it in a centred `<dialog>` modal. The modal header shows: coloured mod-circle + patient name (h2) + type·date·code subtitle + requester physician (from the schedule row, immediately; falls back to `reportData.referrer` after fetch) + clinical indication. The examiner (reporting physician) is appended below the report text as `.report-modal-signed`. Multi-series results get `series-result-title` labels matching the analysis card pattern. The footer has Close and Load Patient buttons. `debounce(fn, ms)` helper is defined at the top of the IIFE.

### HTML / accessibility conventions (`main.html`)

- There is exactly one `<h1>` per visible tab — the content heading (hero title, patient name, tab section title). The brand name uses `<p class="brand-name">`, not `<h1>`.
- Navigation uses `<nav aria-label="Main navigation">` with `aria-current="page"` on the active `<li>` — **not** `role="tablist"` / `role="tab"` / `aria-selected`, because the pattern is link-based and arrow-key tab widget semantics are not implemented.
- Tab panel containers are `<section role="tabpanel" aria-labelledby="...">`. Tab panel section headings carry the `id` referenced by `aria-labelledby`.
- Tab section intro blocks (eyebrow + h1 + action buttons) use `<header>` inside the section. Patient info panels use `<section>` (each has an `<h2>`). Report card sub-sections use `<section>`. The recent-searches block uses `<aside>`. Eyebrow labels use `<p>`, not `<div>`.
- Key-value patient info uses `<dl>`/`<dt>`/`<dd>` — not `<label>` (which is for form controls only).
- `<article>` is reserved for independently distributable content (analysis cards, modal bodies). Tab panel wrappers use `<div>` or `<section>`; markdown containers use `<div>`.
- The `<dialog>` in modal templates has `aria-labelledby` pointing to its `<h2>`.
- No external resource requests. All fonts (Space Grotesk, JetBrains Mono, Inter via `styles.css` `@font-face`) and Font Awesome icons (`static/fontawesome.css` + `static/fonts/fa-solid-900.woff2`) are self-hosted. The favicon is an inline SVG data-URI (hospital icon, indigo `#4338ca`); the same SVG is used in the brand chip. `.fas` rules must include `font-family` and `font-weight: 900` — omitting them produces invisible icons even if the woff2 loads.

### CSS design system

All colours, spacing, radii, and shadows use CSS custom properties defined in `:root` and `[data-theme="dark"]`. Key rules:
- Always use `var(--radius-sm/md/lg/full)` — `var(--radius)` is not defined.
- Always use `var(--font-size-xs/sm/base/lg/2xl/3xl/5xl)` and `var(--font-weight-normal/medium/semibold/bold)` — no hardcoded values.
- Always use `var(--spacing-xs/sm/md/lg/xl/2xl)` for padding/gap/margin — no hardcoded `px` or `rem` values.
- `--header-height: 72px` is defined in `:root`; use it for the sticky nav `top` offset.
- Header brand uses `.brand-name` (not `h1`) — styled by `.brand-name` selector, not `brand-info h1`.
- Header-specific button and badge styles are scoped to `.header .btn-icon` / `.header .badge` to avoid overriding general component styles.
- `--header-primary` / `--header-secondary` are separate from `--primary` / `--secondary` so the header gradient can use darker shades in dark mode without affecting the rest of the UI.
- Modality colours use `--mod-xr`, `--mod-ct`, `--mod-mr`, `--mod-us`, `--mod-fl` (not `--modality-*`) with distinct light and dark values — the light values are darkened to meet WCAG AA 4.5:1 against white; the dark values are lighter for dark backgrounds.
- `@media (prefers-reduced-motion: reduce)` disables all animations and hover transforms; the CSS spinner becomes a static indicator.

### Dual API surface

Every resource type has two route families:
- `/api/<resource>` — returns `HipoData` as plain JSON (internal/debug use)
- `/fhir/<Resource>` — returns FHIR R4 JSON

The `?debug=page` query parameter on any `/api/*` endpoint returns the raw Hipocrate HTML for debugging scrapers.

