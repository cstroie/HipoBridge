# Hipocrate usage survey

Inventory of every outbound call from HippoBridge to Hipocrate: what maps to
what endpoint, when it fires, how many upstream calls it costs, and where
that cost was redundant. See also the "Concurrency and caching" and
"Scraper-specific gotchas" sections in `CLAUDE.md`.

## Client → endpoint mapping

| Client (`hipoclient.py`) | Hipocrate URL | HippoBridge route(s) | Calls / invocation |
|---|---|---|---|
| `HipoClientPatient` | `/Pacient/edit.asp?id=` | `/api/patient/{id}`, `/fhir/Patient/{id}` | 1 |
| `HipoClientPatientSearch` | `/files/search.asp?what=PA` (+`edit.asp` on single hit) | `/api/patient`, `/fhir/Patient` | 1–2 |
| `HipoClientServiceRequest` | `buletinRecoltari.asp?id=` | `/api/request/{id}`, `/fhir/ServiceRequest/{id}` | 1 |
| `HipoClientServiceRequestSearch` | `analysesEpisod.asp` / `analysesALL.asp` per domain | `/api/request`, `/fhir/ServiceRequest` (unfiltered) | **24** (9 imaging + 15 lab domains, parallel) when no `type`/`dt` filter given; 1 otherwise |
| `HipoClientImagingStudy` | `BuletinAnalize.asp?type=3` | `/api/study/{id}`, `/fhir/ImagingStudy/{id}` | 1 direct; FHIR route adds ServiceRequest (+ Cerere fallback) — 2–3 total |
| `HipoClientDiagnosticReport` | `BuletinAnalize.asp?type=1` | `/api/report/{id}`, `/fhir/DiagnosticReport/{id}` | 1; called N times by `ObservationBundle` |
| `HipoClientCheckout` | `BiletExternare.asp` | `/api/checkout/{id}`, Encounter auto-detect (1st probe) | 1 |
| `HipoClientCheckin` | `checkin.asp` | `/api/checkin/{id}`, Encounter auto-detect (2nd probe) | 1 |
| `HipoClientCheckup` | `checkup.asp` | `/api/checkup/{id}` (explicit `?type=` only, not in auto-detect chain) | 1 |
| `HipoClientCerere` | `cerere.asp?id=` | `/api/request/{id}/patient`, `/fhir/ServiceRequest/{id}?type=cerere`, worklist enrichment | 1 |
| `HipoClientPresentation` | `FisaPrezentare.asp` | `/api/presentation/{id}`, Encounter auto-detect (final fallback) | 1 |
| `HipoClientObservationBundle` | 15× `analysesEpisod.asp` (lab domains) + N× `BuletinAnalize.asp` | `/fhir/Observation`, `/api/observation` | **15 + N** on a cold miss (N = lab requests inside the 90-day window), report fetches capped at 5 concurrent; 0 on a hit against its own dedicated bundle cache |
| `HipoClientWhoami` | `Template/menu.asp` | `/api/whoami` | 1 (2 if login needed) on a cold miss; 0 on a hit against the per-username identity cache. The `menu.asp` page itself is still never cached by URL — shared URL, per-user content |
| `HipoClientSchedule` | `PARA/NOM/Listare/?id=44` | `/api/schedule`, `/fhir/Schedule`, worklist refresh | 1 |
| `HipoClientReportWrite` | `Rezultate.asp` (GET then POST) | `POST /api/request/{id}/report` | 2 |
| `HipoClientReportValidate` | `Ajax_Cerere.asp?action=VDV` | `POST /api/request/{id}/validate` | 1 |
| `HipoClientCererePerform` | `cerere.asp` (GET then POST) | `POST /api/request/{id}/perform` | 2 |

Write clients (`ReportWrite`, `ReportValidate`, `CererePerform`) always bypass
the cache and evict downstream `BuletinAnalize.asp`/`cerere.asp` entries on
success.

## Caching model

- One process-wide `URLCache`: 500-entry LRU, 30-min TTL, keyed by exact
  URL (query string included) — **not** per-user. Patient/request/report/
  schedule content isn't permission-scoped per Hipocrate login in this
  system, only `whoami` is user-specific, so a shared cache is correct;
  partitioning it per user would only fragment the 500-entry budget.
- `_NO_PERSIST_PATTERNS` marks a few URL families L1-only (never written to
  the L2 disk cache): whoami (`Template/menu.asp`), patient search
  (`files/search.asp`), and the schedule listing itself
  (`PARA/NOM/Listare/?id=`). `cerere.asp` lives under the same directory
  prefix but is a separate, much more stable page and was previously
  swept into the same no-persist rule by a too-broad substring match —
  narrowed so it now gets normal L1+L2 persistence.
- In-flight de-duplication (`is_inflight`/`wait_inflight`) collapses
  concurrent requests for the same URL to a single upstream fetch.
- `ImagingStudy`, `DiagnosticReport`, and `Checkout` evict their own cache
  entry if the parsed result is empty (report not filled in yet), so an
  unfilled report is never cached and blocks a later, filled fetch.
- Two results get their own dedicated caches outside the shared
  `url_cache`, because they're either too expensive to rebuild or too
  cheap to key by URL:
  - `HipoClientObservationBundle`'s assembled bundle (15+N upstream
    calls to rebuild) lives in its own 100-entry LRU with a 30-min TTL,
    keyed by patient ID, so unrelated traffic against the shared
    500-entry cache can't evict it. `HipoClientReportWrite`,
    `HipoClientReportValidate`, and `HipoClientCererePerform` explicitly
    invalidate a patient's entry on a successful write/validate/perform
    (see N+1 item 8 below) so this cache can't mask a just-written
    report.
  - `HipoClientWhoami`'s parsed identity is cached per username (not by
    URL, since `menu.asp`'s URL is shared across all users) with a 60s
    TTL, explicitly invalidated on logout
    (`UserSessionManager.close_user_session` calls
    `HipoClientWhoami.invalidate_cache`). The underlying `menu.asp` page
    itself is still never left in the shared URL cache.

## N+1 / redundant-fetch patterns found and fixed

1. **Duplicate lab-domain scraping** — `ServiceRequestSearch` (unfiltered)
   and `ObservationBundle` both fetched all 15 lab domains for the same
   patient, but at different page sizes (`NrPePag=100` vs `50`), producing
   different cache keys and re-scraping the same domains twice per
   patient review. **Fixed**: `ObservationBundle` now uses `NrPePag=100`
   to match, so the two paths share cache entries.
2. **Worklist schedule refresh forced eviction on every call** —
   `WorklistRefresher._fetch_schedule` passed `force=True` unconditionally,
   even though `refresh_if_stale`'s own throttle (default 60s) already
   gates whether `refresh()` runs at all. The two mechanisms were
   redundant. **Fixed**: dropped `force=True`; the throttle is now the
   only staleness policy, and the schedule cache can be reused across
   refreshes of different `lab_id`s with overlapping date ranges.
3. **`cerere.asp` inadvertently non-persistent** — see caching model
   above. **Fixed**.
4. **Encounter auto-detect fallback** (`GET /fhir/Encounter/{id}` without
   `?type=`) tries Checkout → Checkin → Presentation sequentially,
   short-circuiting on first success. Left as-is: it already avoids the
   worst case (parallel fan-out) via early exit, and the frontend always
   passes `?type=` so this path is rarely exercised. Enforcing `?type=`
   server-side would be a breaking change for other API consumers.
5. **`get_fhir_imaging_study` fan-out** (ImagingStudy + ServiceRequest +
   conditional Cerere, 2–3 calls) reflects a genuine need for
   justification text from a second source, not literal duplication —
   left as-is.

## Concurrency

- All outbound Hipocrate HTTP calls — user-facing routes, the 24-way and
  15-way fan-outs, login, and worklist enrichment — share one global
  `asyncio.Semaphore(6)`. A single unfiltered `/api/request` or
  `/fhir/Observation` call can itself want up to 15–24 concurrent slots,
  so those fan-outs execute in batches of 6 rather than truly in
  parallel. This is intentional: Hipocrate is fragile under load, so the
  semaphore is left untouched rather than raised.
- The worklist has no fixed-interval poll loop. Refreshes are triggered
  on-demand by real DICOM C-FIND traffic and debounced per `lab_id`
  (`on_demand_refresh_seconds`, default 60s) — Hipocrate load from the
  worklist subsystem scales with actual device queries, not wall clock.

6. **`ObservationBundle` aggregate evicted by unrelated traffic** — its
   result was cached in the shared 500-entry `url_cache`, so a large
   `ServiceRequestSearch`/`ObservationBundle` fan-out for a different
   patient could evict it before reuse, forcing a full 15+N rebuild.
   **Fixed**: moved to its own dedicated 100-entry LRU (see caching
   model above).
7. **`whoami` never cacheable** — every `/api/whoami` call was a full
   live Hipocrate fetch, worst-case with a login probe too; likely
   called on every frontend page load. **Fixed**: added a per-username
   in-memory cache (60s TTL, invalidated on logout) sitting in front of
   the still-uncached `menu.asp` fetch.
8. **`ObservationBundle` cache left stale after a report write** —
   `HipoClientReportWrite`, `HipoClientReportValidate`, and
   `HipoClientCererePerform` evict `BuletinAnalize.asp`/`cerere.asp` by
   request ID on success, but never knew the *patient* ID, so they
   couldn't invalidate that patient's `ObservationBundle` entry. This
   predates the dedicated bundle cache above but got worse once that
   cache became protected from LRU eviction — a written/validated
   report could now be masked by stale `/fhir/Observation` data for the
   full 30-minute TTL instead of being evicted early by chance under
   load. **Fixed**: `ReportWrite`/`ReportValidate` do a cache-only (no
   extra Hipocrate call) lookup of the already-cached `cerere.asp` page
   to recover the patient ID and invalidate their bundle entry;
   `CererePerform` already holds the live `cerere.asp` form fields
   (including `strPacientId`) from its own GET step, so it invalidates
   unconditionally with no lookup needed.
