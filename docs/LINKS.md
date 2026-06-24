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
| `GET /fhir/ValueSet/cnp?id={cnp}` | Validate and parse a Romanian CNP |
| `POST /fhir/md2html` | Convert markdown to HTML (body: markdown text) |

---

## Debug

Two complementary debug mechanisms:

**1. Raw HTML for a proxied endpoint** — append `?debug=page` to any `/api/*` single-resource endpoint:

```
GET /api/patient/421200000683090?debug=page
GET /api/study/1667755?debug=page
GET /api/report/1667755?debug=page
GET /api/checkout/260100000619759?debug=page
GET /api/checkin/652001?debug=page
GET /api/checkup/421200002270746?debug=page
```

**2. Arbitrary Hipocrate path passthrough** — fetch any Hipocrate URL not yet proxied:

```
GET /api/debug?path=/Pacient/history.asp?pacid=421200000667904
GET /api/debug?path=/files/checkin.asp?id=652001
GET /api/debug?path=/files/checkup.asp?cuid=421200002270746
```

Returns the raw Hipocrate HTML. Useful for inspecting pages before writing a parser.

---

## Admission Record (Checkin)

| HippoBridge endpoint | Hipocrate URL |
|---|---|
| `GET /api/checkin/{id}` | `/files/checkin.asp?id={id}` |

Returns: patient name/CNP, presentation date/urgency/section, diagnosis, DRG/72H diagnoses, secondary diagnoses, ward transfers, exam (general/local).

---

## Emergency Consultation (Checkup)

| HippoBridge endpoint | Hipocrate URL |
|---|---|
| `GET /api/checkup/{id}` | `/files/checkup.asp?cuid={id}` |

Returns: patient name/CNP, presentation date/urgency/section, admission info, ICD-10, initial/final/referral diagnoses, discharge status, exam (general/local).

---

## Schedule (worklist)

| HippoBridge endpoint | Hipocrate URL |
|---|---|
| `GET /api/schedule` | `/PARA/NOM/Listare/?id=44&NrPePag=200&LR_requesteddateSD=…&LR_requesteddateED=…&PARA_ID_Laborator=…&PARA_TextCautare=…` |
| `GET /fhir/Schedule` | same |

Query params (both endpoints):

| Param | Type | Description |
|---|---|---|
| `start_date` | `YYYY-MM-DD` | Range start (default: today) |
| `end_date` | `YYYY-MM-DD` | Range end (default: same as start) |
| `lab_id` | integer | Hipocrate lab ID — native filter via `PARA_ID_Laborator` |
| `patient_text` | string | Patient name free-text search via `PARA_TextCautare` |
| `section_name` | string | Exact ward name — server-side Python filter |
| `refresh` | `1` | Evict URL from LRU cache before fetching |

Lab IDs (from `/gen_lib/filtre_ajax_dropdown.asp?N=PARA_ID_Laborator&P1=44`):

| ID | Name |
|---|---|
| 26 | Computer Tomograf |
| 28 | Ultrasound (Ecografie) |
| 32 | Imagistica Rezonanta Magnetica |
| 49 | X-Ray (Radiografie) |
| 35 | Radiologie Interventionala |
| 50 | Radioscopii si Radiografii/Ecografii cu contrast |

FHIR ServiceRequest status mapping:

| Hipocrate | FHIR status |
|---|---|
| Cerere netrimisa | `on-hold` |
| Trimisa in laborator | `draft` |
| Primita in laborator | `draft` |
| In lucru(NV) | `active` |
| Cerere completata | `completed` |
| Cerere completata/partial validata | `completed` |
| Terminata | `ended` (R6) |
| Fara analize | `entered-in-error` |

---

## Request Details (cerere)

| HippoBridge endpoint | Hipocrate URL |
|---|---|
| `GET /api/request/{id}/patient` | `/PARA/NOM/Listare/cerere.asp?id={id}` |
| `GET /fhir/ServiceRequest/{id}?type=cerere` | `/PARA/NOM/Listare/cerere.asp?id={id}` |

Full request edit form. Returns patient name, CNP, demographics (derived from CNP), request date/time, priority, payment type, ordering physician, ward/section, clinical diagnosis, clinical indication, justification, request code, laboratory name, and exam list (when present). Also resolves the numeric `patient.id` — used by the Schedule tab to load a patient record. Returns an access-denied error for labs the authenticated user cannot view (e.g. Ecografie); use `/api/request/{id}` (buletinRecoltari) as fallback for patient demographics in that case.

---

## Known Hipocrate URLs (not yet proxied)

| Purpose | URL |
|---|---|
| Patient history (all analyses) | `/Pacient/analysesALL.asp?type=PA&pacid={id}` |
| Patient admission history | `/Pacient/history.asp?pacid={id}` |
| Lab request detail | `/PARA/NOM/Listare/cerere.asp?id={id}` |
| Appointments list | `/gen_apps/` |
| User info | `/gen_administrare/listare/cont.asp?id={id}&ses=1` |
