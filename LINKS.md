# HippoBridge API & Hipocrate URL Reference

Base URL (HippoBridge): `http://<host>:44660`  
Base URL (Hipocrate): `http://192.168.3.230/hipocrate`

All endpoints require HTTP Basic Auth (`Authorization: Basic ...`).  
Append `?debug=page` to any `/api/*` single-resource endpoint to get the raw Hipocrate HTML.

---

## Patient

| HippoBridge endpoint | Hipocrate URL |
|---|---|
| `GET /api/patient?name={name}` | `POST /files/search.asp?what=PA` |
| `GET /api/patient?q={cnp\|name}` | `POST /files/search.asp?what=PA` (CNP search) |
| `GET /api/patient/{id}` | `/Pacient/edit.asp?id={id}` |
| `GET /fhir/Patient?name={name}` | same |
| `GET /fhir/Patient?q={cnp\|name}` | same |
| `GET /fhir/Patient/{id}` | `/Pacient/edit.asp?id={id}` |

Patient IDs are 15-digit numbers (e.g. `421200000683090`).

---

## Service Requests (analyses list per patient)

| HippoBridge endpoint | Hipocrate URL |
|---|---|
| `GET /api/request?patient={id}` | `/Pacient/analysesEpisod.asp?pacid={id}&strDomeniu={domain}&NrPePag=100` — parallel fetch for all imaging domains |
| `GET /api/request?patient={id}&type={type}` | `/Pacient/analysesEpisod.asp?pacid={id}&strDomeniu={domain}&NrPePag=100` |
| `GET /api/request?patient={id}&dt={datetime}` | `/Pacient/analysesEpisod.asp?pacid={id}&strAN={year}&NrPePag=100` |
| `GET /fhir/ServiceRequest?patient={id}` | same as above |
| `GET /fhir/ServiceRequest?patient={id}&type={type}` | same |
| `GET /fhir/ServiceRequest?patient={id}&dt={datetime}` | same |

Domain codes: `radio=36`, `eco=33`, `ct=32`, `irm=34`, `rads=37`.

Type codes: `radio`, `eco`, `ct`, `irm`, `rads`, `lab`, `rads`, `apa`.

---

## Single Service Request

| HippoBridge endpoint | Hipocrate URL |
|---|---|
| `GET /api/request/{id}` | `/PARA/Printabile/buletinRecoltari.asp?id={id}` |
| `GET /fhir/ServiceRequest/{id}` | `/PARA/Printabile/buletinRecoltari.asp?id={id}` |

---

## Imaging Study (type=2: radio, eco, ct, irm, rads)

| HippoBridge endpoint | Hipocrate URL |
|---|---|
| `GET /api/study/{id}` | `/PARA/Printabile/BuletinAnalize.asp?id={id}&type=2&IdP=1` |
| `GET /fhir/ImagingStudy/{id}` | `/PARA/Printabile/BuletinAnalize.asp?id={id}&type=2&IdP=1` |

Result text is in `studies[].result` (raw API) or `note[].text` (FHIR).  
Validator doctor is in `studies[].validator` (raw API) or `performer[].actor.display` (FHIR).

---

## Diagnostic Report (type=1: lab)

| HippoBridge endpoint | Hipocrate URL |
|---|---|
| `GET /api/report/{id}` | `/PARA/Printabile/BuletinAnalize.asp?id={id}&type=1&IdP=1` |
| `GET /fhir/DiagnosticReport/{id}` | `/PARA/Printabile/BuletinAnalize.asp?id={id}&type=1&IdP=1` |

---

## Encounter / Discharge Summary

| HippoBridge endpoint | Hipocrate URL |
|---|---|
| `GET /api/checkout/{id}` | `/gen_printabile/BiletExternare.asp?RelId={id}&RelName=CO` |
| `GET /fhir/Encounter/{id}` | `/gen_printabile/BiletExternare.asp?RelId={id}&RelName=CO` |

Encounter IDs are 15-digit numbers (e.g. `260100000619759`).

---

## Utilities

| HippoBridge endpoint | Description |
|---|---|
| `GET /fhir/Metadata` | FHIR CapabilityStatement |
| `GET /fhir/spec` | OpenAPI spec (spec.json) |
| `GET /fhir/CodeSystem/analysis-types` | Analysis type codes and domain mappings |
| `GET /fhir/ValueSet/cnp?cnp={cnp}` | Validate and parse a Romanian CNP |
| `POST /fhir/md2html` | Convert markdown to HTML (body: markdown text) |

---

## Debug

Append `?debug=page` to any `/api/*` single-resource endpoint to return the raw Hipocrate HTML instead of parsed JSON. Useful for inspecting page structure when parsers break.

Examples:
```
GET /api/patient/421200000683090?debug=page
GET /api/study/1667755?debug=page
GET /api/report/1667755?debug=page
GET /api/checkout/260100000619759?debug=page
```

---

## Known Hipocrate URLs (not yet proxied)

| Purpose | URL |
|---|---|
| Patient history (all analyses) | `/Pacient/analysesALL.asp?type=PA&pacid={id}` |
| Patient admission history | `/Pacient/history.asp?pacid={id}` |
| Lab request detail | `/PARA/NOM/Listare/cerere.asp?id={id}` |
| Appointments list | `/gen_apps/` |
| User info | `/gen_administrare/listare/cont.asp?id={id}&ses=1` |
