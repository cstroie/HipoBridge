# DICOM Modality Worklist (MWL) Server

HippoBridge includes an optional DICOM Modality Worklist SCP that serves the Hipocrate imaging schedule to physical devices (CT scanners, MRI, ultrasound, X-Ray) via the standard C-FIND protocol (SOP Class `1.2.840.10008.5.1.4.31`). C-ECHO (Verification) is also supported so devices can ping the server before querying.

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
| `accession_prefix` | _(empty)_ | Optional string prepended to the numeric request ID to form the AccessionNumber (e.g. `HB-` → `HB-1721991`). Leave empty for the bare numeric ID |
| `username` | — | Hipocrate username. Can also be set via `HYP_USER` environment variable |
| `password` | — | Hipocrate password. Can also be set via `HYP_PASS` environment variable |

Device profiles are hot-reloaded: edit `worklist.cfg` to add or modify a device section and the change takes effect on the next C-FIND association — no server restart needed.

### Device profiles

One `[SECTION]` per device or logical group:

```ini
[CT_MAIN]
ae_title = CT_SCANNER
modality = CT
wards =
time_window_hours = 48
```

| Key | Description |
|-----|-------------|
| `ae_title` | Calling AE title the device sends (matched case-insensitively) |
| `modality` | DICOM modality code: `CT`, `MR`, `US`, `CR`, `RF`. Determines which Hipocrate lab is queried and which cache slot is read. `RF` covers both Fluoroscopy and Interventional Radiology. Legacy slugs (`eco`, `irm`, `radio`, `fluoro`, `rads`, `ct`) are also accepted |
| `wards` | Comma-separated substrings matched case-insensitively against the Hipocrate ward name (e.g. `ZI` matches `SPITALIZARE DE ZI`). Empty = all wards |
| `time_window_hours` | Exclude entries scheduled more than N hours from now. `0` = no limit |

### Modality reference

| DICOM code | Hipocrate lab ID(s) | Fetch window |
|------------|---------------------|--------------|
| `CT` | 26 | 7 days ahead |
| `US` | 28 | 3 days ahead |
| `MR` | 32 | 7 days ahead |
| `CR` | 49 | 3 days ahead |
| `RF` | 35, 50 | 3 days ahead |

Lookback is always 1 day (yesterday). LAB is intentionally excluded — lab requests do not use a DICOM worklist.

## Access control

**AE Title allowlist** — only devices with a matching `[SECTION]` in `worklist.cfg` are served. Any unknown calling AE title receives a DICOM Failure response (`0xA700`) and a warning in the log:

```
WARNING Worklist.UnknownAE: Rejected C-FIND from unknown AE title 'NEWDEVICE'.
Add a [NEWDEVICE] section to worklist.cfg to authorise this device.
```

To discover a new device's AE title: point it at HippoBridge and let it connect once — the warning log tells you exactly what to add to `worklist.cfg`.

**Future improvement**: add an `ip` key per device section to also validate the source IP address, preventing a rogue host from impersonating a known AE title. The peer address is available via `event.assoc.requestor.address` at association time in pynetdicom.

There is no username/password at the DICOM protocol level. For environments where the worklist crosses a network boundary, consider DICOM TLS with client certificates (`ssl_context` on pynetdicom's `start_server()`).

## Architecture

```
pynetdicom thread (sync)
  handle_find(event)
    → _reload_profiles_if_changed()       # hot-reload on cfg mtime change
    → AE title allowlist check            # unknown → 0xA700 Failure
    → _lab_ids_for_profile(profile)       # DICOM code → [lab_id, ...]
    → _on_demand_refresh(lab_ids)         # asyncio.run_coroutine_threadsafe
        → WorklistRefresher.refresh_if_stale(lab_id)
            → _fetch_schedule(lab_id)     # HipoClientSchedule
            → _enrich(request_id)         # HipoClientCerere → HipoClientPatient
            → _build_datasets(entry, info)# one Dataset per exam
            → WorklistCache.update(lab_id, datasets, raw)
    → WorklistCache.snapshot_multi(lab_ids)
    → _filter(entries, raw, profile, calling_ae)
    → _matches_cfind(ds, identifier)
    → yield 0xFF00, ds                    # C-FIND Pending per match
    → DEBUG log: accession | patient | exam
```

### `WorklistCache`

Per-modality slots: `Dict[lab_id → (datasets, raw_dicts, updated_at)]` under a single `threading.Lock`.

- `update(lab_id, entries, raw)` — replaces one modality's slot; other modalities are untouched
- `snapshot(lab_id)` — returns entries for one modality
- `snapshot_multi(lab_ids)` — merges several slots (used for `RF` which spans two Hipocrate labs)
- `snapshot(None)` — merges all slots (used for unconfigured devices with no modality set)

### `WorklistRefresher`

Runs in the asyncio event loop. Triggered on-demand from the pynetdicom thread via `asyncio.run_coroutine_threadsafe`.

- `refresh(lab_id)` — fetches the schedule for one modality, enriches patient demographics, builds Datasets, updates the cache slot
- `refresh_if_stale(lab_id, max_age_seconds)` — skips the refresh if the slot was updated within the throttle window; protected by a `threading.Lock` so concurrent C-FIND handlers don't all trigger simultaneous fetches

There is no periodic background refresh. The cache is warmed on the first C-FIND for each modality and kept fresh by subsequent device polls.

### `WorklistServer`

pynetdicom `AE` instance. Runs in a daemon thread (`DicomMWL`). Supports C-ECHO (Verification) and C-FIND (MWL).

### Patient enrichment

For each active schedule entry:
1. `HipoClientCerere(request_id)` → `patient.id` + exam names (e.g. `ULTRASONOGRAFIA ABDOMINALA`)
2. `HipoClientPatient(patient_id)` → name, DOB, sex, CNP

`PatientID` is set to the CNP (13-digit Romanian national ID), which falls back to the Hipocrate numeric patient ID. `PatientBirthDate` and sex are derived from the CNP when the patient record itself doesn't provide them — the CNP encodes both.

Results are cached in `_patient_cache` for the lifetime of the entry in the schedule. Falls back to name-only if enrichment fails.

Enrichment runs with `asyncio.Semaphore(2)` — at most 2 patients enriched concurrently, leaving headroom for normal HTTP traffic through the global `_hipocrate_semaphore(6)`.

## DICOM Dataset fields

A single Hipocrate request with multiple exams produces multiple Datasets — one per exam — each with a distinct `ScheduledProcedureStepID` suffix (`request_id-1`, `request_id-2`, …). Single-exam requests produce one Dataset with no suffix. All steps of the same request share the same `AccessionNumber` and `StudyInstanceUID`.

| Tag | Attribute | Source |
|-----|-----------|--------|
| `(0010,0010)` | PatientName | Hipocrate name → DICOM PN (`Family^Given^Middle^Prefix`) |
| `(0010,0020)` | PatientID | CNP (enriched), falls back to Hipocrate numeric patient ID |
| `(0010,0030)` | PatientBirthDate | From patient record; derived from CNP if absent |
| `(0010,0040)` | PatientSex | From patient record; derived from CNP if absent |
| `(0008,0050)` | AccessionNumber | `{accession_prefix}{request_id}` (e.g. `1721991` or `HB-1721991`) |
| `(0008,0090)` | ReferringPhysicianName | `requested_by` → DICOM PN |
| `(0032,1060)` | RequestedProcedureDescription | Exam name from cerere.asp; falls back to lab name |
| `(0020,000D)` | StudyInstanceUID | `1.2.840.99999999.1.{request_id}` |
| `(0040,0100)[n]` | ScheduledProcedureStepSequence | one entry per exam |
| ↳ `(0040,0001)` | ScheduledStationAETitle | calling device AE title (stamped per-query) |
| ↳ `(0040,0002)` | ScheduledProcedureStepStartDate | date part of `date_time` |
| ↳ `(0040,0003)` | ScheduledProcedureStepStartTime | time part of `date_time` |
| ↳ `(0008,0060)` | Modality | DICOM code (`CT`, `US`, `MR`, `CR`, `RF`) |
| ↳ `(0040,0007)` | ScheduledProcedureStepDescription | exam name from cerere.asp |
| ↳ `(0040,0009)` | ScheduledProcedureStepID | `request_id` (or `request_id-N` for multi-exam) |
| ↳ `(0040,1001)` | RequestedProcedureID | same as ScheduledProcedureStepID |

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
# Automated offline tests (no server or credentials needed)
python3 runtests.py worklist

# Verify the live server responds to C-ECHO
echoscu -aet FINDSCU -aec HIPPOBRIDGE 127.0.0.1 11112

# Query by modality and date range
findscu -v -S \
  -k "0008,0052=IMAGE" \
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
