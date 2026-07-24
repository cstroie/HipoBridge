# Hipocrate Site Survey

Mapping of Hipocrate web pages, their URLs, data available, and HippoBridge coverage status.

Survey date: 2026-06-17. All pages use windows-1250 encoding.
Base URL: `http://<host>/Hipocrate/`

---

## Patient demographics — `Pacient/edit.asp?id={patient_id}`

**HippoBridge:** `/api/patient/{id}` → `/fhir/Patient/{id}`

The main patient record (pasaport). All demographic and administrative fields are in a large HTML form.

**Fields available:**
- Identity: `strNume` (family name), `strPrenume` (given names), `strCNP` (Romanian CNP/SSN), `strCID` (electronic health card ID), `strDataNastere` (DOB), `strSexId`
- Identity document: `strActIdentId` (type), `strActIdent_serie`, `strActIdent_nr`
- Contact: `strTelefon`, `strEmail`
- Legal domicile and residence address (county/city/street/nr/bloc/scara/etaj/ap)
- Clinical: `strGreutate` (weight), `strGreutateNastere` (birth weight), `strInaltime` (height), `strGrupaSangeId` (blood group), `strRHId`, `strIdFenotipRhKell`
- Administrative: `strProfesieId`, `strStareCivilaId`, `strReligieId`, `strMCPAN` (GP), `strMedicFamId`
- Medical history: `strAtentie` (alerts), `strAlergii` (allergies), `strObs` (observations), `strAnamneza` (anamnesis)
- GDPR: `strAcordInfoApartinatori`, `strAcordAccesPortal`
- Companion/next-of-kin: `strApartinator_*` (name, CNP, phone, email, address)
- Insurance: `strMCPAN` (health insurance authority)
- Special flags: `strisStrain` (foreign), `strisRezident` (resident), `strisRRRpacient`, `strRRRDesease`, `strINIType`, `Infectie`, `InfectieStatus`, `InfectieDataDepistare`

**Linked from patient page:**
- `../files/presentation.asp?id={presentation_id}` — outpatient presentations
- `../files/checkin.asp?id={checkin_id}` — inpatient admission
- `../files/checkout.asp?id={checkout_id}` — discharge record
- `/Hipocrate/SectionPage.asp?Sc={section_code}` — ward page

---

## Patient search — `files/search.asp?what=PA&strCautare={query}`

**HippoBridge:** `/api/patient?q={query}` (internal search), `/fhir/Patient?q={query}`

Search results table. Each row contains:

| Col | Content |
|-----|---------|
| 0 | Patient ID (link to `Pacient/edit.asp`) |
| 1 | Full name |
| 2 | Sex / age text (e.g. `M / 34 ani`) |
| 3 | Birth date `DD/MM/YYYY` |
| 4 | Current section |
| 5 | Last visit date |
| 6 | Insurance type |

---

## Outpatient presentation — `files/presentation.asp?id={presentation_id}`

**HippoBridge:** `/api/presentation/{id}` (JSON) · `/fhir/Encounter/{id}?type=presentation` (FHIR Encounter)

An outpatient visit / triage record. Linked from the patient page as `Fara nr.Reg` (no registry number) or with a presentation code.

**Fields scraped:**
- Patient name (from `Pacient/edit.asp` header link) and CNP (from input or table row)
- `presentation.date`, `presentation.time`, `presentation.date_time` (combined)
- `presentation.registry` — registry number (`strRefID`)
- `presentation.section` — ward/triage unit (e.g. `UPU`)
- `presentation.medic` — attending physician
- `presentation.is_urgent` — urgency flag
- `presentation.reason` — reason for visit (`Motiv prezentare:`)
- `presentation.consult_type` — consultation type from `sCUType` select
- `presentation.decision` — discharge decision from linked consultation row
- `presentation.checkup_id` — linked checkup ID (`savedCUId`)

**FHIR Encounter:** class `EMER` for UPU/CPU/URGENTA sections, `AMB` otherwise. Period start from date/time; `reasonCode[0].text` = reason for visit; `note[0].text` = decision, `note[1].text` = consult type; `priority` = emergency if urgent.

---

## Inpatient admission — `files/checkin.asp?id={checkin_id}`

**HippoBridge:** `/api/checkin/{id}` (JSON), no FHIR route yet

Full admission form (Fisa Internare). Rich page with multiple embedded tables.

**Top section — admission metadata:**
- `strRefID` / `NRFO` — FO (file number)
- `sCIDate` / `sCITime` — admission date/time
- `DATAINT` — ISO admission datetime
- `CIType` — admission type (e.g. "Trimitere Medic de Familie")
- `strCheckinCriteria` — urgency criteria
- `criteriuA17` — DRG urgency code
- `sMealCode` — diet/meal regime
- `isDayCI` — day hospitalisation flag
- `strPR_BiletSerie` / `strPR_BiletNr` / `strPR_BiletData` — referral letter
- `DaySection` — ward code

**Diagnoses:**
- `strDiagType` — diagnosis type (Acut/Cronic/Subaccut)
- `DiagnosisP` — primary ICD-10 with DRG code, e.g. `G47.30 Apneea de somn... (377)`
- `strCITextDiagnosis` — free-text diagnosis
- Secondary diagnoses list (ICD-10)
- `sDRGDate` — DRG date

**Embedded tables (all on the same page):**

| Table | Content |
|-------|---------|
| Ward movements (Sectia/Regim/De la/Pana la) | Transfer history |
| Checkup consultations | List of `checkup.asp?ciid=&cuid=` links |
| Procedures (Cod examinare / Cod procedura / Nume procedura / Cantitate / Principala / Data efectuarii) | All DRG procedures with DRACO codes |
| Lab analyses | Analysis requests during admission |

**Navigation links:**
- `presentation.asp?id={id}` — linked presentation
- `checkout.asp?id={id}` — discharge form
- `checkup.asp?ciid={checkin_id}&cuid={checkup_id}` — per-consultation exam
- `companions.asp?relname=CI&relID={id}` — companions/visitors during admission
- `../gen_apps/?PacientId=&relid=&relname=CI` — appointment scheduling
- `/Hipocrate/Files/amb_recepy.asp?pid=&ciid=&tip=` — ambulatory prescription

**Not yet scraped by HippoBridge:** ward movements, DRG procedures, lab requests table.

---

## Inpatient discharge — `files/checkout.asp?id={checkout_id}`

**HippoBridge:** `/api/checkout/{id}` scrapes `gen_printabile/BiletExternare.asp` (printable summary), not this edit form

The discharge edit form. Likely contains fields for:
- Discharge date/time, ward, medic
- Discharge status (vindecat/ameliorat/stationar/decedat…)
- Primary and secondary ICD-10 diagnoses (same split as checkin)
- Epicrisis (free-text, HTML)
- Recommendations
- Treatment at discharge
- Insurance settlement info

**What `BiletExternare.asp` gives us** (currently scraped):
- Patient identity + insurance (`insurance_house`, `insurance_category`, `insurance_number`)
- Address, phone
- FO number, urgency flag
- Primary + secondary diagnoses (ICD-10)
- Recommended treatment
- Epicrisis text
- Admission/discharge dates, ward, medic

---

## Outpatient consultation — `files/checkup.asp?cuid={checkup_id}`

**HippoBridge:** `/api/checkup/{id}` (JSON), no FHIR route yet

A per-encounter consultation within an admission (or standalone outpatient visit).

**Fields:**
- `sCUDate` / `sCUTime` — consultation date/time
- `DaySection` — ward at time of consult
- `DayMedic` — physician ID
- `CUType_IdRRR` — consultation type code
- Textarea fields (clinical content): `strICD10DiagnosisName`, `Diagnosis`, `sCUInitDiag` (initial diagnosis), `sCUFinDiag` (final diagnosis), `sCUSendDiag` (referral diagnosis), `sCUValoriP` (physiological values), `CASNr`, `strDecisionDetails`, `strExamenGen` (general exam), `strExamenLoc` (local exam), `sCUDetailsHtmlArea` (details HTML), `sEpicrisysHtmlArea` (epicrisis), `sRecommendationsHtmlArea` (recommendations)

**Navigation links:**
- `companions.asp?relname=CU&relID={id}` — companions for this consultation
- `procedures.asp?cuid={id}` — procedures/manoeuvres
- `amb_recepy.asp?pid=&cuid=&tip=` — ambulatory prescription
- `gen_printabile/FisadeManevre.asp?relid=&relname=CU` — printable manoeuvres sheet
- `/redirect.asp?app=Hdes&link=DESPresentation.asp?…` — link to DES (electronic health record system)

---

## Lab/imaging request slip — `PARA/Printabile/buletinRecoltari.asp?id={request_id}`

**HippoBridge:** `/api/request/{id}` → `/fhir/ServiceRequest/{id}`

Printable collection slip for lab or imaging.

**Fields:**
- Section, requesting physician, registration physician
- Request date/time
- Request code (e.g. `EH4756`)
- FO number, patient name, CNP, age
- Diagnosis (ICD-10 code + text)
- Urgency flag
- Ordered tests (name, type/sample, quantity)
- Payment type (Chitanta / Spital / etc.)

---

## Analysis result buletin — `PARA/Printabile/BuletinAnalize.asp?id={id}&type=1` (lab) or `&type=3` (imaging)

**HippoBridge:** `/api/report/{id}` (type=1, DiagnosticReport) · `/api/study/{id}` (type=3, ImagingStudy)

The result document. Both types use the same URL with `type` param.

**Shared header fields:**
- Collection date/time, arrival date/time
- Request code, buletin status (FINAL / PARTIAL)
- Payment category
- Patient: name, CNP, phone, age, patient code
- Urgency, sex, section, requesting medic
- Clinical indication (`INFO SUPLIMENTAR:` footer note)

**Type 1 (lab `DiagnosticReport`):** structured results per analyte (name, value, reference range, unit, sample type, method).

**Type 2 (imaging `ImagingStudy`):** free-text radiologist report per series (series description, result narrative). Multiple series per study are possible.

---

## Schedule / request list — `PARA/NOM/Listare/?id=44&NrPePag=200`

**HippoBridge:** `/api/schedule` → `/fhir/Schedule`

Lists lab/imaging requests for a date range. One row per request.

**Columns per row:**
- Patient name (link to `Pacient/edit.asp`)
- Request code (link, e.g. `ES9686`)
- Request ID (from link href)
- Date/time (`DD/MM/YYYY HH:MM`)
- Status (`Cerere netrimisa` / `Trimisa in laborator` / `In lucru(NV)` / `Cerere completata` / `Terminata` / `Fara analize`)
- Payment type
- Priority (`Normala` / `Urgenta`)
- Section (ward)
- Requesting physician
- Laboratory name (maps to modality slug)

**Native server-side filters:** `PARA_ID_Laborator` (lab ID), `PARA_TextCautare` (patient text), `PARA_Ordonare=2` (sort).
**Python-side filter:** `section_name` (exact ward match).

---

## Request edit form — `PARA/NOM/Listare/cerere.asp?id={request_id}`

**HippoBridge:** `/api/request/{id}/patient` (full HippoData JSON) · `/fhir/ServiceRequest/{id}?type=cerere` (FHIR ServiceRequest)

The full request edit form. Fully implemented: patient name, CNP, demographics (derived from CNP), request date/time, priority, payment type, ordering physician, section, diagnosis, clinical indication, justification, and ordered exam list.

Hipocrate renders only the selected `<option>` per `<select>` (no `selected=` attribute) — field extraction reads the first `<option>` text. Exam list is loaded dynamically and is usually empty in static HTML; four fallback patterns are preserved for edge cases.

---

## Companions — `files/companions.asp?relname={CI|CU}&relID={id}`

**HippoBridge:** not implemented

Lists companions/visitors registered during an admission (`relname=CI`) or consultation (`relname=CU`).

**Likely fields:** companion name, relationship, CNP, phone, period of presence.

---

## Procedures — `files/procedures.asp?cuid={checkup_id}`

**HippoBridge:** not implemented

Standalone procedures page for a checkup. (Procedures are also embedded in the `checkin.asp` page.)

**Fields:** DRACO procedure codes, descriptions, quantities, dates. Same structure as the embedded table in checkin.

---

## Ambulatory prescription — `files/amb_recepy.asp?pid={patient_id}&cuid={checkup_id}&tip=`

**HippoBridge:** not implemented

Prescription issued at an outpatient consultation.

**Likely fields:** medication name, dose, frequency, duration, prescribing physician, prescription date/number.

---

## Discharge medication — `files/FMD_medicatie.asp?ciid={checkin_id}`

**HippoBridge:** not implemented

Medication at discharge (referenced from checkin page). Separate from the treatment text in BiletExternare.

**Likely fields:** medication list with doses, start/stop dates, route of administration.

---

## Risk assessment — `files/EvaluareRisc.asp?ciid={checkin_id}`

**HippoBridge:** not implemented

Risk assessment form linked from the admission. Likely contains standard clinical risk scores (fall risk, pressure ulcer, nutritional status, etc.).

---

## Ward page — `/Hipocrate/SectionPage.asp?Sc={section_code}`

**HippoBridge:** not implemented

Per-ward overview page. Shows current patients in a section. Useful for census/bed management, not per-patient clinical data.

---

## Appointments — `gen_apps/?PacientId={id}&relid={checkin_id}&relname=CI`

**HippoBridge:** not implemented

Appointment scheduling linked from the admission. Shows scheduled appointments for a patient.

---

## Analysis evolution — `analyse/evolution/show.asp?popup=yes&strPacient={id}`

**HippoBridge:** not implemented

Trend view for a patient's lab results over time. Useful for longitudinal analysis (e.g. haemoglobin, creatinine trends).

---

## Bed management — `files/checkin_beds.asp?IdHipocrate={checkin_id}`

**HippoBridge:** not implemented

Bed assignment for an admission. Shows which physical bed was occupied and when.

---

## Ward transfers — `files/transfer.asp?id=&cid={checkin_id}`

**HippoBridge:** not implemented (transfer data is partially embedded in `checkin.asp`)

Explicit transfer record between wards during a single admission. Ward movement history is partially available in the checkin form's embedded table.

---

## Printable manoeuvres sheet — `gen_printabile/FisadeManevre.asp?relid={id}&relname=CU`

**HippoBridge:** not implemented

Printable summary of procedures/manoeuvres for a consultation. Same data as the procedures table, formatted for printing.

---

## User / whoami — `Template/menu.asp`

**HippoBridge:** `/api/whoami`

Sidebar menu iframe. Provides authenticated user identity.

**Fields:** `user.display_name` (from `<small>` under CONTUL MEU), `user.id` (from `cont.asp?id=(\d+)` link), `user.username` (from Basic Auth, not from the page).

**Security note:** `/gen_administrare/listare/cont.asp?id={user.id}&ses=1` exposes full employee record including plaintext password — **do not scrape**.

---

## Logout — POST `security/logon.asp` (or close session)

**HippoBridge:** `POST /api/logout` — closes the caller's Hipocrate session via `user_session_manager.close_user_session(username)`.

---

## Summary: HippoBridge coverage

| Page | Hipocrate URL | HippoBridge route | Status |
|------|--------------|-------------------|--------|
| Patient demographics | `Pacient/edit.asp` | `/api/patient/{id}`, `/fhir/Patient/{id}` | ✅ Full |
| Patient search | `files/search.asp?what=PA` | `/api/patient?q=`, `/fhir/Patient?q=` | ✅ Full |
| Lab/imaging request slip | `PARA/Printabile/buletinRecoltari.asp` | `/api/request/{id}`, `/fhir/ServiceRequest/{id}` | ✅ Full |
| Request details (cerere) | `PARA/NOM/Listare/cerere.asp` | `/api/request/{id}/patient`, `/fhir/ServiceRequest/{id}?type=cerere` | ✅ Full |
| Lab result (DiagnosticReport) | `BuletinAnalize.asp?type=1` | `/api/report/{id}`, `/fhir/DiagnosticReport/{id}` | ✅ Full |
| Imaging result (ImagingStudy) | `BuletinAnalize.asp?type=3` | `/api/study/{id}`, `/fhir/ImagingStudy/{id}` | ✅ Full |
| Discharge summary (printable) | `gen_printabile/BiletExternare.asp` | `/api/checkout/{id}`, `/fhir/Encounter/{id}` | ✅ Full |
| Inpatient admission form | `files/checkin.asp` | `/api/checkin/{id}` | ⚠️ JSON only, no FHIR, no procedures |
| Outpatient consultation | `files/checkup.asp` | `/api/checkup/{id}` | ⚠️ JSON only, no FHIR |
| Schedule / request list | `PARA/NOM/Listare/?id=44` | `/api/schedule`, `/fhir/Schedule` | ✅ Full |
| User identity | `Template/menu.asp` | `/api/whoami` | ✅ Full |
| Logout | session close | `POST /api/logout` | ✅ Full |
| Outpatient presentation | `files/presentation.asp` | `/api/presentation/{id}`, `/fhir/Encounter/{id}?type=presentation` | ✅ Full |
| Discharge edit form | `files/checkout.asp` | — | ❌ Not implemented (BiletExternare covers key fields) |
| Companions/visitors | `files/companions.asp` | — | ❌ Not implemented |
| Procedures (standalone) | `files/procedures.asp` | — | ❌ Not implemented |
| Ambulatory prescription | `files/amb_recepy.asp` | — | ❌ Not implemented |
| Discharge medication | `files/FMD_medicatie.asp` | — | ❌ Not implemented |
| Risk assessment | `files/EvaluareRisc.asp` | — | ❌ Not implemented |
| Appointments | `gen_apps/` | — | ❌ Not implemented |
| Analysis trends | `analyse/evolution/show.asp` | — | ❌ Not implemented |
| Bed assignment | `files/checkin_beds.asp` | — | ❌ Not implemented |
| Ward transfers | `files/transfer.asp` | — | ❌ Not implemented (partial data in checkin) |
| Ward page | `SectionPage.asp` | — | ❌ Not implemented |
| Manoeuvres sheet (print) | `gen_printabile/FisadeManevre.asp` | — | ❌ Not implemented (data in checkup) |

---

## High-value candidates for future implementation

1. **Procedures in checkin** (`checkin.asp` embedded table) — DRACO procedure codes, dates, quantities. Already scraped, not yet exposed in HippoData/FHIR.
2. **Discharge medication** (`FMD_medicatie.asp`) — medication list at discharge, richer than BiletExternare treatment text.
3. **Analysis trends** (`analyse/evolution/show.asp`) — longitudinal lab values per patient. Useful for clinical summary.
4. **Ambulatory prescription** (`amb_recepy.asp`) — prescriptions issued at outpatient consultations.
5. ~~**Request edit form** (`cerere.asp`)~~ — ✅ implemented (`/api/request/{id}/patient`, `/fhir/ServiceRequest/{id}?type=cerere`).
6. ~~**Outpatient presentation** (`presentation.asp`)~~ — ✅ implemented.
