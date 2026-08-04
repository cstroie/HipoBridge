# HippoBridge

HippoBridge is a scraping proxy that exposes a FHIR R4 API and a web interface on top of the legacy Hipocrate medical system. It has no database — every request authenticates against Hipocrate, scrapes HTML, and returns structured JSON or FHIR resources.

## Installation & running

```bash
./install         # one-time: creates .python venv, installs requirements.txt
./hippobridge start
```

See [INSTALL.md](INSTALL.md) for prerequisites, configuration, CLI flags, and running as a systemd/OpenRC service.

## Web interface

Open `http://localhost:44660` to access the single-page app. Navigation:

- **Schedule** — daily imaging/lab worklist; always visible; filters by date range, modality chips, status chips, ward (dropdown), patient name (Enter to search); clicking a request code opens the exam report in a modal (coloured modality circle, patient name, requester, indication, report text, examiner signature); clicking a patient name loads the patient
- **Patient Search** — search by CNP, patient code, or name; multiple results show a keyboard-accessible selection dialog
- **Patient Profile** — demographics, encounter counts, related requests from the loaded schedule, QR codes, hospitalisation history
- **Imaging** / **Lab** — separate tabs, cards grouped by modality/section; radiologists (per `[radiology] allowed_radiologists`) get Perform/Cancel/Edit/Validate controls on imaging cards; clicking a request code opens a detail popup
- **Epicrisis** — all encounters with an epicrisis, most-recent first, rendered as markdown
- **Report** — full clinical document (patient header + discharge summaries + imaging studies) formatted for LLM consumption
- **AI** — pre-exam analysis brief generated from the Report tab's assembled clinical text; AI executive-summary and Copy-as-Markdown buttons also appear on the Report/Epicrisis/Lab tabs
- Three-state theme toggle: auto (OS preference) → light → dark
- Respects `prefers-reduced-motion`; all fonts and icons served locally — no external requests

## API

Most resources have two routes:

| Route | Returns |
|---|---|
| `GET /api/<resource>` | Raw `HippoData` JSON (internal/debug) |
| `GET /fhir/<Resource>` | FHIR R4 JSON |

Exceptions: `/fhir/Metadata`, `/fhir/spec`, `/fhir/CodeSystem/analysis-types`, and `/fhir/md2html` are meta/utility endpoints, not resources, so there's nothing to pair them with.

Add `?debug=page` to any `/api/*` single-resource endpoint to get the raw Hipocrate HTML.

Key endpoints:

```
GET  /fhir/Patient?q={search_term}
GET  /fhir/Patient/{id}
GET  /fhir/ServiceRequest?patient={id}[&type={code}][&region={region}][&dt={iso_datetime}]
GET  /fhir/ServiceRequest/{id}               — BuletinSolicitare.asp (region, indication, ordering physician)
GET  /fhir/Task/{id}                         — cerere.asp (workflow state: status, execution period, itemized exams, report)
GET  /fhir/Specimen/{id}                     — buletinRecoltari.asp (lab/imaging handoff paperwork; stretch of the resource, no physical specimen)
GET  /fhir/DiagnosticReport/{id}
GET  /fhir/ImagingStudy/{id}
GET  /fhir/Encounter/{id}[?type=checkout|checkin|checkup|presentation]
GET  /fhir/Observation?patient={id}[&start_date=&end_date=&refresh=1]  — aggregated lab observations
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
GET  /api/request/{id}/patient  — full request details from cerere.asp (patient name, CNP, priority, clinical indication, physician, section, report text, performed date, validate toggles)
GET  /api/checkin/{id}          — admission record (checkin.asp)
GET  /api/checkup/{id}          — emergency consultation (checkup.asp)
GET  /api/debug?path=...        — raw Hipocrate HTML passthrough for any path
GET  /api/whoami                — logged-in user info; includes can_write_reports flag
GET  /api/specimen/{id}         — raw counterpart of /fhir/Specimen/{id}
GET  /api/cnp?id={cnp}          — raw counterpart of /fhir/ValueSet/cnp (same handler, mounted twice)
POST /api/logout                — close the caller's Hipocrate session
GET  /api/cache/stats           — URLCache size/hit stats
POST /api/cache/cleanup         — evict expired cache entries
POST /api/request/{id}/perform  — mark exam as performed (sets DataEfectuarii to now); radiologists only
POST /api/request/{id}/cancel   — cancel a request (replays cerere.asp's own Anulează action); radiologists only
POST /api/request/{id}/report   — write/update report HTML for an analysis; radiologists only
POST /api/request/{id}/validate — toggle validation state for a report; radiologists only
POST /api/ai/summarize          — AI summary for a report/epicrisis/imaging/lab/pre-exam text block
POST /api/ai/summarize/stream   — same, streamed via SSE
```

### Radiology report workflow

The write endpoints are restricted to usernames listed under `[radiology] allowed_radiologists` in `hippobridge.cfg`. The `/api/whoami` response includes `can_write_reports: true` when the user is in this list — the web interface uses this to gate the action buttons.

Workflow: **Perform → Write → Validate**, or **Cancel** in place of Perform to withdraw the request. Each step replays the `cerere.asp` form with the appropriate field override; caches for `cerere.asp` and `BuletinAnalize` are evicted after every write.

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
python3 client.py -u USER -w PASS --cnp {cnp}
```

No `--checkin`/`--checkup` flags — those endpoints are reachable via the HTTP API (`/api/checkin/{id}`, `/api/checkup/{id}`) but not wired into this CLI.

`--patient` accepts a patient code, a 13-digit CNP (validated then resolved to a code), or a partial CNP ending with `*`.

## DICOM Modality Worklist

HippoBridge can serve the imaging schedule to CT, MRI, ultrasound, and X-Ray devices via the DICOM MWL protocol (C-FIND, SOP Class `1.2.840.10008.5.1.4.31`), so technicians don't type patient demographics at the console.

The MWL server starts automatically alongside the HTTP server when `worklist.cfg` is present. Copy `worklist.cfg.example` to get started. See [WORKLIST.md](WORKLIST.md) for full documentation.

```bash
pip install pynetdicom pydicom
cp worklist.cfg.example worklist.cfg   # fill in credentials and device sections
```

## Running tests

```bash
python3 runtests.py               # all groups
python3 runtests.py extractors    # offline
python3 runtests.py markdown      # offline
python3 runtests.py hippodata     # offline
python3 runtests.py worklist      # offline
python3 runtests.py llm           # offline
```

Groups requiring a live server: `root`, `auth`, `patients`, `analyses`, `reports`, `checkout`, `checkin`, `checkup`, `cnp`.

## Acknowledgements

- [aiohttp](https://docs.aiohttp.org/) — async HTTP server and client
- [Beautiful Soup 4](https://www.crummy.com/software/BeautifulSoup/) — HTML scraping
- [marked.js](https://marked.js.org/) — client-side Markdown rendering
- [Inter](https://rsms.me/inter/) by Rasmus Andersson — UI typeface
- [Space Grotesk](https://floriankarsten.github.io/space-grotesk/) by Florian Karsten — display typeface
- [JetBrains Mono](https://www.jetbrains.com/lp/mono/) by JetBrains — monospace typeface
- [Font Awesome 6](https://fontawesome.com/) — icons (Free / solid subset)
- [HL7 FHIR R4](https://hl7.org/fhir/R4/) — resource model and API conventions
- [pynetdicom](https://pydicom.github.io/pynetdicom/) — DICOM network stack (MWL SCP)
- [pydicom](https://pydicom.github.io/pydicom/) — DICOM Dataset construction

## License

Internal hospital use only.
