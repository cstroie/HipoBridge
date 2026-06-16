# HippoBridge

HippoBridge is a scraping proxy that exposes a FHIR R4 API and a web interface on top of the legacy Hipocrate medical system. It has no database — every request authenticates against Hipocrate, scrapes HTML, and returns structured JSON or FHIR resources.

## Prerequisites

- Python 3.8+
- Access to a Hipocrate instance
- Hipocrate credentials

## Installation

```bash
pip install -r requirements.txt
```

## Running the server

```bash
export HYP_USER=<username> HYP_PASS=<password>
python3 hipobridge.py
```

Server listens on `http://0.0.0.0:44660` by default. Set `LOG_LEVEL=DEBUG` for verbose logging. Override host/port/service URL with `local.cfg` (not tracked by git):

```ini
[server]
port = 8080

[hipocrate]
service_url = http://192.168.3.230/hipocrate
```

## Web interface

Open `http://localhost:44660` to access the single-page app. Navigation:

- **Schedule** — daily imaging/lab worklist; always visible; filters by date range, modality chips, ward (dropdown), patient name (Enter to search); clicking a request code opens the exam report in a modal (coloured modality circle, patient name, requester, indication, report text, examiner signature); clicking a patient name loads the patient
- **Patient Search** — search by CNP, patient code, or name; multiple results show a keyboard-accessible selection dialog
- **Patient Profile** — demographics and encounter counts
- **Analyses** — imaging and lab cards grouped by modality; clicking a request code opens a detail popup
- **Epicrisis** — all encounters with an epicrisis, most-recent first, rendered as markdown
- **Report** — full clinical document (patient header + discharge summaries + imaging studies) formatted for LLM consumption
- Three-state theme toggle: auto (OS preference) → light → dark
- Respects `prefers-reduced-motion`; no external font requests (system font stack)

## API

Every resource has two routes:

| Route | Returns |
|---|---|
| `GET /api/<resource>` | Raw `HipoData` JSON (internal/debug) |
| `GET /fhir/<Resource>` | FHIR R4 JSON |

Add `?debug=page` to any `/api/*` endpoint to get the raw Hipocrate HTML.

Key endpoints:

```
GET  /fhir/Patient?q={search_term}
GET  /fhir/Patient/{id}
GET  /fhir/ServiceRequest?patient={id}[&type={code}][&region={region}][&dt={iso_datetime}]
GET  /fhir/ServiceRequest/{id}
GET  /fhir/DiagnosticReport/{id}
GET  /fhir/ImagingStudy/{id}
GET  /fhir/Encounter/{id}
GET  /fhir/Schedule[?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&lab_id=N&section_name=S&patient_text=T&refresh=1]
GET  /fhir/ValueSet/cnp?id={cnp}
GET  /fhir/CodeSystem/analysis-types
POST /fhir/md2html
GET  /fhir/Metadata
GET  /fhir/spec
```

Raw-JSON-only endpoints (no FHIR equivalent yet):

```
GET  /api/schedule[?start_date=&end_date=&lab_id=&section_name=&patient_text=&refresh=1]
GET  /api/request/{id}/patient  — resolve numeric patient ID from a request page
GET  /api/checkin/{id}          — admission record (checkin.asp)
GET  /api/checkup/{id}          — emergency consultation (checkup.asp)
GET  /api/debug?path=...        — raw Hipocrate HTML passthrough for any path
```

`/fhir/Schedule` returns a `searchset` Bundle of `ServiceRequest` resources. Modality filter uses Hipocrate's native `PARA_ID_Laborator` param; patient text uses `PARA_TextCautare`; ward is filtered server-side by name. Pass `?refresh=1` to bypass the 30-minute LRU cache.

All endpoints require HTTP Basic Auth.

## CLI client

Credentials can be passed as flags or via `HYP_USER` / `HYP_PASS` environment variables.

```bash
python3 client.py -u USER -w PASS --search "patient_name"
python3 client.py -u USER -w PASS --patient {id|CNP|partial_CNP*}
python3 client.py -u USER -w PASS --analyses {patient_id} [--analysis-type radio] [--datetime-filter 2025-03-15]
python3 client.py -u USER -w PASS --report {id}
python3 client.py -u USER -w PASS --imaging-study {id}
python3 client.py -u USER -w PASS --checkout {id}
python3 client.py -u USER -w PASS --checkin {id}
python3 client.py -u USER -w PASS --checkup {id}
python3 client.py -u USER -w PASS --cnp {cnp}
```

`--patient` accepts a patient code, a 13-digit CNP (validated then resolved to a code), or a partial CNP ending with `*`.

## Running tests

```bash
python3 runtests.py               # all groups
python3 runtests.py extractors    # offline
python3 runtests.py markdown      # offline
python3 runtests.py hipodata      # offline
```

Groups requiring a live server: `root`, `auth`, `patients`, `analyses`, `reports`, `checkout`, `cnp`.

## License

Internal hospital use only.
