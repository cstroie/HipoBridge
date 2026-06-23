# DICOM Modality Worklist (MWL) Server

HippoBridge includes an optional DICOM Modality Worklist SCP that serves the Hipocrate imaging schedule to physical devices (CT scanners, MRI, ultrasound, X-Ray) via the standard C-FIND protocol (SOP Class `1.2.840.10008.5.1.4.31`).

Devices query the worklist instead of having technicians type patient demographics manually at the console. Each device sees only its own modality's slice of the schedule, filtered by ward and time window.

## Prerequisites

```bash
pip install pynetdicom pydicom
```

If these packages are not installed, the MWL server is silently disabled and the main HTTP server starts normally.

## Setup

```bash
cp worklist.cfg.example worklist.cfg
$EDITOR worklist.cfg          # fill in credentials and device sections
python3 hipobridge.py         # MWL server starts automatically alongside the HTTP server
```

`worklist.cfg` is listed in `.gitignore` and must never be committed — it contains Hipocrate credentials.

## Configuration

### `[worklist]` section

| Key | Default | Description |
|-----|---------|-------------|
| `ae_title` | `HIPPOBRIDGE` | DICOM AE Title this server presents to devices (max 16 chars, uppercase) |
| `port` | `11112` | TCP port. 11112 needs no root; 104 requires root or `CAP_NET_BIND_SERVICE` |
| `on_demand_refresh_seconds` | `60` | Minimum seconds between Hipocrate fetches triggered by a C-FIND. Queries within this window reuse the cached result |
| `username` | — | Hipocrate username. Can also be set via `HYP_USER` environment variable |
| `password` | — | Hipocrate password. Can also be set via `HYP_PASS` environment variable |

### Device profiles

One `[SECTION]` per device or logical group:

```ini
[CT_MAIN]
ae_title = CT_SCANNER
modality = ct
wards =
time_window_hours = 48
```

| Key | Description |
|-----|-------------|
| `ae_title` | Calling AE title the device sends (matched case-insensitively) |
| `modality` | DICOM modality code: `CT`, `MR`, `US`, `CR`, `RF`. Determines which Hipocrate lab is queried and which cache slot is read. `RF` covers both Fluoroscopy and Interventional Radiology. Both old slugs (`eco`, `irm`, etc.) and DICOM codes are accepted |
| `wards` | Comma-separated substrings matched case-insensitively against the Hipocrate ward name (e.g. `ZI` matches `SPITALIZARE DE ZI`). Empty = all wards |
| `time_window_hours` | Exclude entries scheduled more than N hours from now. `0` = no limit |

### Modality slugs

| DICOM code | Hipocrate lab ID(s) | Internal slug(s) | Fetch window |
|------------|--------------------|--------------------|--------------|
| `CT` | 26 | `ct` | 7 days |
| `US` | 28 | `eco` | 3 days |
| `MR` | 32 | `irm` | 7 days |
| `CR` | 49 | `radio` | 3 days |
| `RF` | 35, 50 | `rads`, `fluoro` | 3 days |

Fetch window is the lookahead from today. Lookback is always 1 day (yesterday).

LAB is intentionally excluded — lab requests do not use a DICOM worklist.

## Access control

**AE Title allowlist** — only devices with a matching `[SECTION]` in `worklist.cfg` are served. Any unknown calling AE title receives a DICOM Failure response (`0xA700`) and a warning in the log:

```
WARNING Worklist.UnknownAE: Rejected C-FIND from unknown AE title 'FINDSCU'.
Add a [FINDSCU] section to worklist.cfg to authorise this device.
```

Once the device's AE title is known, add a section to `worklist.cfg`. No server restart is required — config is re-read on each association.

**Future improvement**: add an `ip` key per device section to also validate the source IP address, preventing a rogue host from impersonating a known AE title. The peer address is available via `event.assoc.requestor.address` at association time in pynetdicom.

There is no username/password at the DICOM protocol level. For environments where the worklist crosses a network boundary, consider DICOM TLS with client certificates (`ssl_context` on pynetdicom's `start_server()`).

## Architecture

```
pynetdicom thread (sync)
  handle_find(event)
    → _lab_id_for_profile(profile)
    → _on_demand_refresh(lab_id)          # asyncio.run_coroutine_threadsafe → asyncio loop
        → WorklistRefresher.refresh_if_stale(lab_id)
            → _fetch_schedule(lab_id)     # HipoClientSchedule via existing scraping layer
            → _enrich(request_id)         # HipoClientCerere → HipoClientPatient
            → _build_dataset(entry, info) # pydicom Dataset
            → WorklistCache.update(lab_id, datasets, raw)
    → WorklistCache.snapshot(lab_id)
    → _filter(entries, raw, profile, calling_ae)
    → _matches_cfind(ds, identifier)
    → yield 0xFF00, ds                    # C-FIND Pending per match
```

### `WorklistCache`

Per-modality slots: `Dict[lab_id → (datasets, raw_dicts, updated_at)]` under a single `threading.Lock`.

- `update(lab_id, entries, raw)` — replaces one modality's slot; other modalities are untouched
- `snapshot(lab_id)` — returns entries for one modality
- `snapshot(None)` — merges all slots (used for unconfigured devices with no modality set)

### `WorklistRefresher`

Runs in the asyncio event loop. Triggered on-demand from the pynetdicom thread via `asyncio.run_coroutine_threadsafe`.

- `refresh(lab_id)` — fetches the schedule for one modality, enriches patient demographics, builds Datasets, updates the cache slot
- `refresh_if_stale(lab_id, max_age_seconds)` — skips the refresh if the slot was updated within the throttle window; protected by a `threading.Lock` so concurrent C-FIND handlers don't all trigger simultaneous fetches

There is no periodic background refresh. The cache is warmed on the first C-FIND for each modality and kept fresh by subsequent device polls.

### `WorklistServer`

pynetdicom `AE` instance. Runs in a daemon thread (`DicomMWL`). Handles one C-FIND event type.

- Unknown AE titles → `0xA700` Failure, return
- Known profile → on-demand refresh → snapshot → filter → C-FIND Pending per match

### Patient enrichment

For each active schedule entry:
1. `HipoClientCerere(request_id)` → `patient.id` (numeric Hipocrate ID)
2. `HipoClientPatient(patient_id)` → name, DOB, sex, CNP

Results are cached in `_patient_cache` (keyed by `request_id`) for the lifetime of the entry in the schedule. Falls back to name-only if enrichment fails.

Enrichment runs with `asyncio.Semaphore(2)` — at most 2 patients enriched concurrently, leaving headroom for normal HTTP traffic through the global `_hipocrate_semaphore(6)`.

## DICOM Dataset fields

| Tag | Attribute | Source |
|-----|-----------|--------|
| `(0010,0010)` | PatientName | `patient_name` → DICOM PN (`Family^Given^Middle^Prefix`) |
| `(0010,0020)` | PatientID | `patient.id` (enriched) or `request_id` as fallback |
| `(0010,0030)` | PatientBirthDate | `patient.birth_date` (enriched) |
| `(0010,0040)` | PatientSex | `patient.sex` (enriched) |
| `(0008,0050)` | AccessionNumber | `request_code` (e.g. `ES9686`) |
| `(0008,0090)` | ReferringPhysicianName | `requested_by` → DICOM PN |
| `(0032,1060)` | RequestedProcedureDescription | laboratory display name |
| `(0020,000D)` | StudyInstanceUID | `1.2.840.99999999.1.{request_id}` |
| `(0040,0100)[0]` | ScheduledProcedureStepSequence | see below |
| ↳ `(0040,0001)` | ScheduledStationAETitle | calling device AE title (stamped per-query) |
| ↳ `(0040,0002)` | ScheduledProcedureStepStartDate | date part of `date_time` |
| ↳ `(0040,0003)` | ScheduledProcedureStepStartTime | time part of `date_time` |
| ↳ `(0008,0060)` | Modality | DICOM code from `_MODALITY_CODE[slug]` |
| ↳ `(0040,0007)` | ScheduledProcedureStepDescription | laboratory display name |
| ↳ `(0040,0009)` | ScheduledProcedureStepID | `request_id` |
| ↳ `(0040,1001)` | RequestedProcedureID | `request_id` |

### C-FIND matching keys honoured

| Tag | Attribute | Match type |
|-----|-----------|------------|
| `(0010,0010)` | PatientName | Case-insensitive substring (wildcards `*`/`?` stripped) |
| `(0010,0020)` | PatientID | Exact |
| `(0008,0050)` | AccessionNumber | Exact |
| `(0040,0002)` in SPS | ScheduledProcedureStepStartDate | DICOM date range (`YYYYMMDD` or `YYYYMMDD-YYYYMMDD`) |
| `(0008,0060)` in SPS | Modality | Exact |

All other keys in the C-FIND identifier are silently ignored.

### Status filtering

Only entries with an active Hipocrate status reach the device:

| Hipocrate status | FHIR status | Included |
|-----------------|-------------|---------|
| Cerere netrimisa | `on-hold` | yes |
| Trimisa / Primita in laborator | `draft` | yes |
| In lucru(NV) | `active` | yes |
| Cerere completata | `completed` | **no** |
| Terminata | `ended` | **no** |
| Fara analize | `entered-in-error` | **no** |

## Name conversion

Romanian physician and patient names are converted to DICOM PN format (`Family^Given^Middle^Prefix`) by `_name_to_dicom()`:

- Input is typically `"DR. POPESCU ION"` or `"PROF. DR. IONESCU MARIA"`
- Title prefixes (`DR`, `PROF`, `CONF`, `SL`, `S.L`, `AS`, `ASIST`, `UNIV`, `ACAD`, `ING`, `EC`) are detected and placed in the fourth PN component
- Glued prefixes like `DR.POPESCU` are split before tokenising
- No trailing `^` when the fifth (suffix) component is empty

## Testing

```bash
# Verify the server is listening
findscu -v -S -k "0008,0052=IMAGE" \
  -k "ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartDate=20260101-20261231" \
  -k "ScheduledProcedureStepSequence[0].Modality=CT" \
  -aet FINDSCU -aec HIPPOBRIDGE \
  127.0.0.1 11112

# Query by patient name
findscu -v -S \
  -k "0008,0052=IMAGE" \
  -k "PatientName=POPESCU*" \
  -k "ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartDate=" \
  -k "ScheduledProcedureStepSequence[0].Modality=" \
  -aet FINDSCU -aec HIPPOBRIDGE \
  127.0.0.1 11112
```

`FINDSCU` must have a matching `[FINDSCU]` section in `worklist.cfg` or the association will be rejected.

## Future improvements

- **IP allowlist** — validate source IP per device profile (see Access control section above)
- **DICOM TLS** — mutual TLS with client certificates for cross-network deployments (`ssl_context` on pynetdicom `start_server()`)
- **MPPS SCP** — Modality Performed Procedure Step (`1.2.840.10008.3.1.2.3.3`) to receive start/complete notifications from devices; currently not implemented (status passthrough via Hipocrate is sufficient)
