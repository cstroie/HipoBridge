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

Server listens on `http://0.0.0.0:44660` by default. Override with `local.cfg` (not tracked by git):

```ini
[server]
port = 8080

[hipocrate]
service_url = http://192.168.3.230/hipocrate
```

## Web interface

Open `http://localhost:44660` to access the single-page app. Features:

- Patient search by CNP, patient code, or name; multiple results show a keyboard-accessible selection dialog
- Patient profile with analyses, diagnostic reports, and epicrisis (all encounters, most-recent first)
- Report tab — assembles a full clinical document (patient header + discharge summaries + imaging studies) formatted for LLM consumption
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
GET  /fhir/ValueSet/cnp?id={cnp}
GET  /fhir/CodeSystem/analysis-types
POST /fhir/md2html
```

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
