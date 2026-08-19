# Architecture

HippoBridge is a **scraping proxy** — no database. Every request authenticates against Hipocrate, scrapes HTML, returns JSON or FHIR R4.

```
HTTP client → hippobridge.py (@require_auth) → HippoClient* (cache + semaphore) → fhir.py → response
```

## Client routing table

| Class | Route | Hipocrate URL |
|---|---|---|
| `HippoClientPatient` | `/api/patient/{id}` | `/Pacient/edit.asp?id={id}` |
| `HippoClientPatientSearch` | `/api/patient?q=` | `/files/search.asp?what=PA` |
| `HippoClientBuletinSolicitare` | `/api/request/{id}`, `/fhir/ServiceRequest/{id}` | `/PARA/Printabile/BuletinSolicitare.asp?id={id}&type=63&IdP=70` |
| `HippoClientServiceRequestSearch` | `/api/request?patient=` | `/Pacient/analysesEpisod.asp` |
| `HippoClientImagingStudy` | `/api/study/{id}` | `/PARA/Printabile/BuletinAnalize.asp?id={id}&type=3` |
| `HippoClientDiagnosticReport` | `/api/report/{id}` | `/PARA/Printabile/BuletinAnalize.asp?id={id}&type=1` |
| `HippoClientCheckout` | `/api/checkout/{id}` | `/gen_printabile/BiletExternare.asp?RelId={id}&RelName=CO` |
| `HippoClientCheckin` | `/api/checkin/{id}`, `/fhir/Encounter/{id}?type=checkin` | `/files/checkin.asp?id={id}` |
| `HippoClientCheckup` | `/api/checkup/{id}`, `/fhir/Encounter/{id}?type=checkup` | `/files/checkup.asp?cuid={id}` |
| `HippoClientPresentation` | `/api/presentation/{id}`, `/fhir/Encounter/{id}?type=presentation` | `/gen_printabile/FisaPrezentare.asp?relname=PR&id={id}` |
| `HippoClientCerere` | `/api/request/{id}/patient`, `/fhir/Task/{id}` | `/PARA/NOM/Listare/cerere.asp?id={id}` |
| `HippoClientServiceRequest` | `/api/specimen/{id}`, `/fhir/Specimen/{id}` | `/PARA/Printabile/buletinRecoltari.asp?id={id}` |
| `HippoClientReportWrite` | `POST /api/request/{id}/report` | `/PARA/NOM/Listare/cerere.asp` (POST) |
| `HippoClientReportValidate` | `POST /api/request/{id}/validate` | `/PARA/NOM/Listare/cerere.asp` (POST action=VDV) |
| `HippoClientCererePerform` | `POST /api/request/{id}/perform`, `POST /api/request/{id}/cancel` | `/PARA/NOM/Listare/cerere.asp` (form replay via shared `_replay_form()`: perform sets DataEfectuarii + hdnAction=S; cancel sets hdnAction=A, mirrors the "Anulează" button) |
| `HippoClientSchedule` | `/api/schedule`, `/fhir/Schedule` | `/PARA/NOM/Listare/?id=44&NrPePag=100` |
| `HippoClientObservationBundle` | `/fhir/Observation?patient=` | `/Pacient/analysesEpisod.asp` (parallel per domain) |
| `HippoClientWhoami` | `/api/whoami` | `Template/menu.asp` |

## Concurrency and caching (critical — Hipocrate is fragile)

- **Semaphore**: `_hipocrate_semaphore = asyncio.Semaphore(6)` — all outbound calls including login.
- **URLCache** (`urlcache.py`): LRU 500 entries, 30-min TTL. In-flight deduplication via `asyncio.Event` — `resolve_inflight()` **must** be called on every exit path including re-auth failures or waiters hang permanently. Optional L2 backing store is duck-typed (`get`/`put`/`remove`), attached via `.fs_cache`.
- **SqliteCache** (`sqlcache.py`, 2026-08-13): the L2 backing store — one SQLite table per scraped-page kind (`cache_patient`, `cache_checkin`, `cache_checkout`, `cache_cerere`, ...) keyed by full URL, plus `cache_ai` for AI summaries. Replaced the earlier JSON-file-per-key `FilesystemCache`. `route()` maps a URL to `(table, record_key)` via a declarative regex table — the single place that knows the URL-shape-to-table mapping, since `cache_get`/`cache_put` only ever see a bare URL. Single persistent WAL-mode connection for the process lifetime (`cache.db`, plus `cache.db-wal`/`cache.db-shm` sidecars — normal, not corruption), guarded by one `threading.Lock` since sqlite3 connections aren't safe across threads and calls arrive via `asyncio.to_thread`. `/api/cache/stats` exposes a `by_table` breakdown.
- **UserSessionManager**: one `aiohttp.ClientSession` per username; per-user `asyncio.Lock` prevents concurrent login sequences.
- `login_if_needed(force=True)` skips the is-logged-in `main.asp` probe when session is known-expired.
- `DICOM_MODALITY` dict maps type codes to `(DICOM_code, human_display)` — never repeat the code string as display value.

## Key module gotchas

**`fhir.py`**:
- `Resource.__setitem__(key, None)` removes the key — never stores `None`.
- `OperationOutcome.from_error()` default code is `"processing"`. Pass explicit code for `"not-found"`, `"required"`, etc.
- `Encounter` uses R4 field names: `period`, `reasonCode`, `reasonReference`, `hospitalization` — not R5 names.

**`hippodata.py`**:
- `store()` strips strings, unwraps single-item lists, converts `datetime` → ISO, skips `None`. Dot-notation creates nested dicts.
- `get(key)` defaults to `None` — callers that need `""` must pass it explicitly.
- `set_success()` removes the `message` key rather than setting it to `""`.

**`extractors.py`**: `parse_date_time` handles Romanian month abbreviations including `Noi` for November.

**`markdown.py`**: `html_to_markdown` decomposes icon-only `<i>` tags; `markdown_to_html` uses STX/ETX sentinels for bold/italic ordering.

**`search.py`** (2026-08-13): Local full-text search over epicrisis/imaging report text — Hipocrate has no search API of its own to proxy (`files/search.asp` and the schedule's `PARA_TextCautare` both match only patient name/CNP, never report body text; see `docs/SITE_SURVEY.md`). Scoped to whatever text has already passed through this server, not a bulk crawl. The write hook lives in `hippoclient.py`'s `HippoClientCheckout`/`HippoClientImagingStudy.fetch_and_parse()` overrides (via `search.schedule_index()`, fire-and-forget so a broken index never affects the actual scrape response), **not** in the `hippobridge.py` route handlers — the frontend only ever calls the `/fhir/Encounter/{id}?type=checkout` and `/fhir/ImagingStudy/{id}` routes, and both of those construct the same client classes as `/api/checkout/{id}`/`/api/study/{id}`, so hooking the client method is the one choke point that actually covers real traffic. Lab reports (`get_report`, `type=1`) are deliberately excluded — those are numeric value/reference-range tables, not narrative text. SQLite FTS5 with `unicode61 remove_diacritics 2` tokenization, so a search matches regardless of which Romanian diacritic variant (ș/ş, ț/ţ) was typed. Piggybacks entirely on `[cache] dir`/`max_age_days` — no config keys of its own, `search.instance` stays `None` (feature silently disabled) when no cache dir is configured, same gating as `ai_cache`. `GET /api/search/text` doesn't itself talk to Hipocrate, so unlike every other route it can't rely on Hipocrate rejecting bad credentials — it independently validates via a (cached) `HippoClientWhoami` call before searching, since a bare presence-of-a-Basic-header check would otherwise let anyone with network access to the server read out indexed PHI. `_backfill_search()` (`hippobridge.py`) rides along on `_periodic_cache_cleanup()`'s existing loop (startup, then every 24h — no separate timer) and scans the disk cache (`SqliteCache.iter_entries()`, `sqlcache.py`) for checkout/imaging pages not yet indexed, catching anything the live `schedule_index()` hook above missed (e.g. a transient indexing failure, or a page that entered the cache some other way). Two layers keep repeat scans cheap: `iter_entries(since_mtime=...)` takes a cursor — persisted in `search.db`'s own `meta` table via `get/set_backfill_cursor_sync()` — so each run only walks cache rows written since the last run instead of every table; and within whatever it does walk, already-indexed `(kind, source_id)` pairs are still skipped without re-parsing their HTML. Runs as a background task off the event loop (never blocks a request or server startup); disable with `--no-search-backfill` if even the first (unavoidably full) scan is too costly on a very large pre-existing cache.

**`llm/`** (AI summary buttons — report/epicrisis/imaging/lab/pre_exam):
- Current production model: **`mistralai/ministral-3-3b` at Q4_K_M** (set in `llm.cfg`'s `[provider:lmstudio]`, `default`/`medical` tiers). Chosen after an extensive benchmark survey — see `docs/llm_benchmark_2026-07-19.md` for the full methodology, per-kind fidelity scores, and model comparisons. Runner-up/fallback candidates: `medgemma-4b-it` (resident for xrayvision, so zero cold-load) and `google/gemma-3n-e4b`.
- **Do not "optimize" by dropping to a smaller quantization** — IQ4_XS and Q3_K_M were benchmarked and are *slower* on this model (more complex quant schemes cost more per-token dequant compute than they save in memory bandwidth at batch-size-1), with no quality upside. Stay on Q4_K_M.
- Prompts live in `llm/prompts/<kind>.md`, not hardcoded in `prompts.py` — edit the `.md` file to tune a prompt, no code change needed. Each kind's prompt is **fully self-contained** (its own role framing, its own restated anti-hallucination rule, its own no-reasoning instruction) — there is deliberately **no shared preamble** prepended to every kind. An earlier design *did* share one (`llm/prompts/system.md`, since deleted); A/B testing (`benchmark_prompt_format.py`, `docs/llm_benchmark_2026-07-21.md`) showed it measurably diluted medgemma-4b-it's language-instruction-following on the short `imaging` kind. `_build_messages()` appends the date directive (if `DATE_AWARE_KINDS`) then the language directive directly after the kind's task prompt — no shared text ahead of it.
- A kind's `.md` file may reference the concrete configured language via a literal `{language}` placeholder (see `pre_exam.md`) — substituted with a targeted `str.replace`, not `str.format`, so a prompt containing unrelated literal braces can't break.
- **Known unresolved limitation**: medgemma-4b-it regresses to the source language (Romanian) on `pre_exam` specifically, on long, source-language-heavy input (~7500 chars). Three escalating prompt-wording fixes were tried and verified live, none fixed it — likely volume-driven language drift, not a wording/ordering problem. `gemma-3n-e4b` handles the same input correctly. **Prefer `gemma-3n-e4b` or `ministral-3-3b` over medgemma-4b-it for `pre_exam`** until this is understood further (see `docs/llm_benchmark_2026-07-21.md`).
- `has_meaningful_content()` (`llm/prompts.py`) gates every call — never hand the model near-empty input; a small model will confidently fabricate an entire scenario (including demographics) rather than say there's nothing to summarize.
- `DATE_AWARE_KINDS`/`STREAMING_KINDS` (`llm/prompts.py`) are deliberately separate constants even though currently identical sets — one is about date context, the other about transport.
- The 4096-token context ceiling is real: an oversized input makes LM Studio return an SSE `event: error` line with no `choices` key, not a normal completion — `ServerBackend.chat_stream()`/`chat()` must check for `chunk.get("error")` explicitly or the failure is silently swallowed.
- This LM Studio instance also serves another project (xrayvision radiology). A model can be evicted mid-generation under radiology load, surfacing as `RuntimeError: terminated` — not a prompt/quality bug. `benchmark_prompt_format.py` retries this a bounded number of times with backoff.
- `ServerBackend.chat`/`chat_stream` request bodies set **both** `"reasoning": {"effort": "none"}` **and** the flat `"reasoning_effort": "none"` — reasoning-capable models otherwise burn tokens on hidden thinking before the visible completion, eating into the 4096-token ceiling. Servers disagree on which shape they read: verified live against LM Studio (`192.168.3.238:1234`) that the nested `reasoning.effort` object, `effort: "off"`, `exclude`, `enable_thinking` (top-level and in `chat_template_kwargs`), `thinking`, and `thinking_budget` all had **zero effect** on `gemma-4-e2b-it` — it kept reasoning regardless, e.g. burning 57 of a 60-token `imaging` budget and returning empty content. Only the flat `reasoning_effort` string field (valid values: `none, minimal, low, medium, high, xhigh`) actually suppressed it. Sending both forms together is harmless — an unrecognized field is just ignored — so this covers the widest range of OpenAI-compatible servers.

### LM Studio Server & Model Selection (2026-07-22 findings)

**Server info endpoint**: `http://192.168.3.238:1234/api/v1/models` — check `loaded_instances` to see which models are currently active.

**medgemma-4b-it behavior**:
- ✅ Reliable for pre_exam (lead with clinical question, surface seizure-like events, safety flags) — produces concise, grounded output with correct age, full translation, no fabrication on rich cases
- ❌ Struggles with report.md (executive summary from discharge record) — does not compress to 3-5 sentences; either outputs raw source text (untranslated Romanian) or produces verbose clinical detail instead of radiologist-focused summary
- **Root issue**: medgemma's language instruction-following (documented weakness in benchmark_2026-07-21.md) makes it unreliable for high-compression tasks (discharge summary). It can do detail-preserving translation (pre_exam) but cannot reliably abstract/summarize.

**Recommendation**: Route `report.md` to `gemma-3n-e4b` or `ministral-3-3b` (both handle compression/abstraction better). Keep medgemma-4b-it for pre_exam (it works well there). Update `llm.cfg` `[provider:lmstudio]` tier assignments accordingly, or wire report specifically to a better model.

**Validation methodology**: Empirically tested both pre_exam and report.md prompts on 50 real pediatric discharge records. pre_exam validated clean (no fabrication, correct demographics, proper translation, safety flags surfaced). report.md validation showed medgemma cannot meet the (then-current) "3-5 sentence executive summary" requirement — produces either raw input or 900+ char verbose output instead.

### report.md / epicrisis.md refactor (2026-07-23)

Both prompts were rewritten per `_testing_/final50/{REPORT,EPICRISIS}_PROPOSALS.md` (a 50-case gap analysis, not tracked in git). Validated against `ministral-3:3b` on the `ct` provider, both on narrative-only input and on real production-shaped composite input (narrative + real Recent Labs + real Recent Imaging sections, pulled live from the server) — not just synthetic fixtures.

- `report.md`: length target tightened from "3-5 sentences" to a firm **2-3**, with the outcome/current-status stated early so truncation can't delete it (was silently dropping the outcome on the richest cases at the old target + 220-token budget). Added an explicit no-fabricated-recommendations rule, extended the copy-verbatim rule to family-history relations, added priority ordering for clinician-emphasized facts over routine logistics, made placeholder-demographic omission mechanical, and clarified that lab/vital-heavy records with little narrative prose still count as meaningful content (fixed a reproducible false-negative "Insufficient clinical information" on a real, dense, non-empty case).
- `epicrisis.md`: gained a 5th, conditional **Flag** line for safety/procedure-relevant facts that don't fit Admission/Diagnosis/Treatment/Outcome (MRI-incompatible hardware, allergies, substance use, family cancer history) — the 4-field format had no home for these and was silently dropping them, including an MRI-safety fact `report.md` caught on the identical source text. Also restructured the field-definition block (was an inline `**Label:** description` block that the model would echo verbatim as if it were example text) and added a concrete filled example.
- **Residual, not prompt-fixable**: on real dense records, ministral still occasionally fabricates a procedure/diagnosis name under compression (e.g. renaming a laparoscopic cystectomy to "cholecystectomy" and inventing "teratoma") or invents an expansion for an undefined source abbreviation. Same category as medgemma's `pre_exam` language-drift issue above — a model-capability ceiling, not something a further wording change reliably fixes. Track alongside the existing model-routing recommendations rather than adding more rules chasing this specific model's idiosyncrasies.

## Entry point conventions

- **Dual-level logging**: the root logger is always set to `DEBUG` (`hippobridge.py:69`) so nothing is filtered before handlers see it; the *console* handler is what actually applies `LOG_LEVEL`/`--log-level` (default `INFO`) via `_console_handler.setLevel(...)`. If `[logging] file` (or `--log-file`) is set, the `RotatingFileHandler` is hardcoded to `DEBUG` regardless of console level — so the file always captures everything (including `Worklist.*` and pydicom's `warn_and_log` warnings) even when the console is quieter. Never hardcode `DEBUG` on the console handler itself.
- File logging is off by default; set `[logging] file` in `hippobridge.cfg` (or `--log-file`) to enable the size-limited `RotatingFileHandler` (`max_bytes`/`backup_count`, default 10MB × 5). Wired in `init_app()`.
- **Startup model survey**: `init_app()` calls `_ai_client.list_models()` right after building the LLM client and logs every model the server currently reports, plus an `available`/`NOT FOUND on server` check per configured tier (`lite`/`default`/`medical`). A failed survey (server cold/unreachable) only logs a warning — it's diagnostic, not fatal, since the server may come up before the first real AI call.
- Config loads in `init_app()`, not at import time.
- File paths: `os.path.join(os.path.dirname(__file__), ...)`.
- Credentials: `request['auth_credentials']` (aiohttp dict-style), not a plain attribute.
- `web_fhir_response(str)` → 400 OperationOutcome. Don't pass strings for server-side failures.
- `web_json_response`: `status="success"` → 200; "not found" in message → 404; other errors → 500.

## Error handling

- `OperationOutcome` HTTP status: `not-found` → 404; `error`/`fatal` severity → 500; `warning` → 400.
- `HippoClientDiagnosticReport` and `HippoClientCheckout` evict cache on empty result.
- Datetime comparisons use naive datetimes — strip `tzinfo` if caller passes TZ-aware strings.
- Never swallow exceptions in `fetch_and_parse` — log and include in returned `HippoData`.

## Scraper-specific gotchas

**Whoami**: Evicts the shared cache URL before and after each fetch (same URL for all users, user-specific content).

**Security**: `/gen_administrare/listare/cont.asp?id={user.id}&ses=1` echoes the user's password in plaintext (`strParola`) — do not scrape or expose this page.

**Cerere**: `cerere.asp` renders only the selected `<option>` with no `selected=` attribute — `_select_text()` takes the first `<option>` text.

**Schedule**:
- `html.parser` does not inject `<tbody>` — iterate `table.find_all('tr')` directly.
- Lab IDs are hardcoded (CT=26, US=28, MRI=32, X-Ray=49, IR=35, Fluoro=50) — do not guess.
- Ward filtering is Python-side (`?section_name=`); lab and patient-text filters are native Hipocrate URL params.
- **2026-07-28 → reverted 2026-08-14**: Hipocrate removed the "Solicitat de"/"Laborator" columns from the per-request detail table on 2026-07-28 (7 `<td>`s, not 8/9), then restored them on 2026-08-14 *and* added two more: the detail row is now 9 `<td>`s — `Data | Status | Tip plata | Prioritate | Sectie | Data Efectuarii | Cerut de | Laborator | Numar analize`. During the outage window, `HippoClientSchedule.parse_data` only read the first 5 cells and gated everything on `len(detail_cells) >= 7`; it now reads all 9 defensively (index-guarded past cell 4, so a future outage degrades gracefully to the first 5 fields instead of dropping the row).
  - **`Laborator` (cell 7)** is now the primary modality source, via `_LABORATORY_LABEL_TO_MODALITY` (Romanian display text → internal slug, confirmed live per lab_id: "Computer Tomograf"→ct, "Ecografie"→eco, "Imagistica Rezonanta Magnetica"→irm, "Radiografie"→radio, "Radiologie Interventionala"→rads, "Radioscopii si Radiografii/Ecografii cu contrast"→fluoro). `_LAB_ID_TO_MODALITY` (the `PARA_ID_Laborator` filter → slug mapping) is now only a fallback for when the row's own text is blank/unrecognized.
  - Because modality is readable per row again, the "all labs" fan-out (`_fetch_and_parse_all_labs`: one concurrent fetch per known lab_id, deduped + merged) was removed — confirmed live that a single **unfiltered** fetch (`PARA_ID_Laborator=''`) returns the exact same row set as the union of all 6 filtered fetches, each row self-labeled. `fetch_and_parse` now always does one fetch; `lab_id` is purely an optional server-side filter (the frontend's lab dropdown), no longer required to discover modality. `_schedule_fanout_semaphore`, `_inaccessible_labs`, and `_lab_failure_streak` (the adaptive per-user "can't see this lab" skip-list, needed only because the fan-out could partially fail per lab) were removed as dead code — a single fetch just returns whatever the user is authorized to see, no per-lab permission tracking needed.
  - **`Cerut de` (cell 6)** populates `requested_by` directly again — confirmed live it's the same value as `cerere.asp`'s `strMedicId` (Medic curant), **not** the true orderer (Medic solicitant). The frontend shows it immediately (no more hidden-until-lazy-fetch flash) but still stashes `regionLine._requesterEl`/`_requesterSep` unconditionally so the `BuletinSolicitare.asp` lazy fetch (see below) can still overwrite it with Medic solicitant when that differs.
  - **`Data Efectuarii` (cell 5)** → new `performed_at` field: the exam-performed timestamp, populated even while `status` still just says "Trimisa in laborator" (staff haven't gotten around to flipping the request's own status text yet) — this was the original motivation for wanting the field: a stale/no-longer-valid request (e.g. a patient who left UPU before approval) would otherwise be indistinguishable from one still legitimately waiting to be worked.
    - **What "active"/"In progress" means** (`HippoClientSchedule._derive_fhir_status()`) is now the union of two independent signals, not a single field: (1) Hipocrate's own raw status text already says so — `"in lucru(nv)"`/`"in lucru(pv)"` map straight to `active` via `_FHIR_STATUS`, unchanged from before; or (2) raw status is still `draft` (`"trimisa in laborator"`/`"primita in laborator"`, i.e. "In lab") but `performed_at` is non-empty — promoted `draft` → `active` since the performed-date is a more current signal than Hipocrate's own status text. Deliberately narrow: only `draft` gets promoted. `performed_at` set alongside `on-hold` (`"cerere netrimisa"`, never even sent) or `entered-in-error` (`"fara analize"`, no analyses) would be a stranger, more surprising combination than a lagging status update, so those are left as-is rather than silently folded into `active` too. Used by both `_apply_filters` (so `?status=active` matches consistently) and `fhir_response`.
  - **`Numar analize` (cell 8)** → new `analysis_count` field (int or `None`), not yet surfaced in the frontend.
- The schedule row's lazy per-row fetch (`scheduleExamObserver`, triggered when a row scrolls into view) is a single request to `/fhir/ServiceRequest/{id}` (`HippoClientBuletinSolicitare` → `BuletinSolicitare.asp`, the request/order form, title "FISA DE SOLICITARE") — gives region (`Organ tinta / segment anatomic`), indication (`Justificare`), and **the correct ordering physician** in one request. `type=63&IdP=70` are fixed and work across modalities (verified on eco/radio/ct) despite the page always being titled "FISA SOLICITARE ECOGRAFIE".
- `bodySite` is not the raw `Organ tinta` text (e.g. "ULTRASONOGRAFIA ABDOMINALA (INCLUSIV PELVIS)") — `fhir_response` runs it through `identify_study_type_and_region()` (the same `regions.cfg`-driven abstraction `ImagingStudy`'s `series.bodySite` uses) to get the short label ("Abdomen", "Chest") the schedule timeline showed before this endpoint switch. Omitted entirely when the region can't be identified (`region == "unknown"`), matching `ImagingStudy`'s own guard — don't fall back to the raw organ text there, that was never the prior behavior.
- **Medic curant vs. Medic solicitant**: `cerere.asp`'s `strMedicId` (`HippoClientCerere` → `request.physician`) only ever resolves to **Medic curant**, the patient's attending physician — never **Medic solicitant**, the physician who actually placed this specific order. The two differ whenever the patient's regular doctor isn't the one who ordered the exam (confirmed on live requests). Only `BuletinSolicitare.asp` distinguishes them. `HippoClientBuletinSolicitare.fhir_response` sets `requester` from Medic solicitant, falling back to Medic curant only if no distinct orderer was recorded — `worklist.py`'s `_enrich()` does the same for the DICOM worklist's `ReferringPhysicianName` (see **worklist.py** below). Task's `requester` (`cerere.asp` → `request.physician`) is still Medic curant — that field genuinely represents the attending physician handing the task off, not the orderer, so it's correct as-is.
- `BuletinAnalize.asp?type=2` was inspected as a candidate for region/indication and rejected: its `MEDIC:` header field is Medic curant too (not the orderer), and the actual performer only appears as `Validat de:` once a report is finalized — not present on an unperformed row.
- `HippoClientBuletinSolicitare.fhir_response`'s indication priority chain (`justification` > `clinical_situation` > `diagnosis_referral`) must filter candidates through `hippoclient.is_meaningful_text()`, not plain truthiness — an unfilled `Justificare` field on the form renders as the literal placeholder `"-"`, which is truthy and would otherwise always win over a real `Situatie clinica` value further down the chain. `is_meaningful_text()` (moved from `hippobridge.py`, which now imports it) is the shared "has at least one letter/digit" filter used for this placeholder-junk problem across the codebase.

**DiagnosticReport / ObservationBundle**: `_parse_observation_value` is shared. Frontend detects lab entries by presence of `reference` key in `presentedForm`, not by `type="lab"` — immunology is typed `"other"` but still has `reference`.

**worklist.py**: Check `parse_cnp()` result via `parsed.get('valid')`, not `parsed.get('status')`. `wards` (not `sections`) key for ward filtering. `resolve_inflight()` must be called from `WorklistRefresher` exit paths too.
- `_enrich()` fetches `BuletinSolicitare.asp` (`HippoClientBuletinSolicitare`) alongside `cerere`/patient/checkin per request, specifically for `request.physician_solicitant` — the true ordering physician, distinct from `cerere.asp`'s `request.physician` (Medic curant, the attending physician). `info['physician']` prefers the former, falling back to the latter only when no distinct orderer was recorded. `_build_datasets`' `ReferringPhysicianName` reads `patient_info['physician']`, so it gets the correct orderer too (see the Medic curant vs. Medic solicitant note above).
- dedup/sort: After `_fetch_schedule`, entries are deduplicated by `request_id` (first occurrence wins) and sorted numerically by `request_id` before enrichment.

**Encounter route**: `?type=checkout|checkin|presentation` skips to right scraper. Without hint: tries all three in sequence (noisy logs). Frontend always passes `?type=`.

**Radiology report workflow** (cerere.asp write path):
- Access controlled by `_ALLOWED_RADIOLOGISTS` — a set of usernames from `[radiology] allowed_radiologists` in config. All three write endpoints (perform/report/validate) return 403 for non-members. `GET /api/whoami` returns `can_write_reports: true` when the authenticated user is in this set.
- **Perform**: `HippoClientCererePerform` GETs cerere.asp, extracts all form fields (skipping submit/button/image/reset; only checked checkboxes/radios), then POSTs back with `DataEfectuarii` overridden and `hdnAction=S`. JS validation in the browser blocks empty `DataEfectuarii`, but the server accepts it without `strSituatieNeincadrabila`/`Justificare`. Evicts cerere.asp and BuletinAnalize caches after POST. `performed_at` is always omitted from the frontend's POST body — the server always stamps `now()` (`HippoClientCererePerform.perform`'s default); a picker for a custom past timestamp was tried and deliberately dropped as unwanted complexity, `now()` is considered safe. Perform and Cancel buttons lock each other while either is in flight (both disabled together, not just the clicked one) since they act on the same request.
- **Cancel**: same class, same form-replay mechanism (`_replay_form()`), but POSTs with `hdnAction=A` and no field overrides — mirrors Hipocrate's own "Anulează" button (captured from a live browser POST body). **2026-08-10** (confirmed live, cerere 1743583): a cancelled request's `cerere.asp` *does* self-report it — the header div's "Status :" field reads `Cerere anulata`, and a separate `#divError` banner reads `CEREREA ESTE ANULATA` — both now extracted by `HippoClientCerere.parse_data` into `request.status_text` and a flat `cancelled` boolean, exposed via `/api/request/{id}/patient`. The frontend's `article.dataset.cancelled`/`modal.dataset.cancelled` local flag (set right after a successful `/cancel` call) is now only an optimistic fallback for the gap before the next fetch confirms it — the previous design relied on the local flag alone, which didn't survive a reload or a different tab/user.
- **Write**: `HippoClientReportWrite.write()` POSTs to Rezultate.asp. Frontend sends the textarea's plain text as-is (no client-side conversion) — `marked.parse()` must never be run before POSTing, only the read path renders markdown. **2026-08-09** (re-confirmed live against report #1729398, superseding the 2026-07-28 disable note): the Rezultat field is a literal HTML sink with no markdown interpretation of its own — raw `\n` is stripped with no substitute whitespace, and `**`/`*` are stored as literal text — so `_text_to_report_html()` converts markdown to real HTML server-side before posting (`**bold**`→`<b>`, `*italic*`→`<i>`, lines joined with `<br>`, chosen over `<div>`-per-line since both shapes were seen on real human-authored reports and the field stores either verbatim). Active and in use, not disabled.
- **Validate**: POSTs `action=VDV` to cerere.asp. Evicts both BuletinAnalize and cerere.asp caches.
- `performed_at` comes from `DataEfectuarii` input on cerere.asp. If blank (old exam done via Hipocrate UI), frontend also treats `allValidated` as implicit performed to suppress the Perform button.

## Frontend (`static/`)

SPA: `main.html` + `scripts.js` + `styles.css` + `marked.js`. All assets self-hosted — no external requests.

**Critical rules:**
- **Never** `new Date(hipocrate_string)` — non-ISO strings produce `RangeError`. Always use `formatDate()` / `formatDateWithTime()`.
- **`calculateAge`** uses string splitting on `YYYY-MM-DD` — never `new Date(birthDate)`.
- **No `innerHTML`** with interpolated strings — use `<template>` + `cloneNode(true)` + `textContent`.
- **No `id` attributes inside `<template>`** — duplicated on every clone.
- Card type is in `article.dataset.type`, read by `filterAnalyses` — don't detect from `className`.
- Lab filter chip (`data-filter="lab"`) requires matching `<option value="lab">` in `#analysesFilter` or it silently no-ops.
- `SPARSE_THRESHOLD = 100` chars — checkin block is sparse if shorter, shows Last Admission stacked below.
- Multiple patient search results must show selection overlay — never silently pick `entry[0]`.
- Imaging history is always unfiltered; lab requests are limited to within 90 days of most recent result.
- **Current episode boundary** (`computeCurrentEpisodeBoundary`/`getEpisodeBoundary`, near `extractCheckinIds`): centralizes what was previously a duplicated "active admission" heuristic (Report tab + Epicrisis tab) into one memoized-per-patient helper, and extends it to outpatient-only patients (no checkin/checkout at all) via gap-based date clustering — `EPISODE_GAP_DAYS = 60` is the tunable threshold, same declaration pattern as `SPARSE_THRESHOLD`. Precedence: an active admission always wins; else a recent-enough last discharge; else the most recent date cluster; else `null` (no signal, renders ungrouped). Drives the Imaging/Lab grid "Current Episode"/"Prior Episodes" dividers and the Report tab's §3/§4 scoping. Because grid data for labs is already capped to the 90-day window above, Lab tab grouping only ever splits within that narrow window — true multi-year historical lab grouping isn't possible there without relaxing the 90-day cutoff; Report §4 is unaffected since it queries `/fhir/Observation` directly, with no such cap.
- `presentedForm` with `reference` key = lab entry regardless of `type` field.
- `.fas` rules need both `font-family` and `font-weight: 900` or icons are invisible.
- Nav uses `aria-current="page"` on `<li>`, not `role="tablist"` / `role="tab"` / `aria-selected`.
- All DOM elements cached at startup in `elements` — never query inside repeated functions.
- `whoamiReady` is a Promise that resolves after `fetchWhoami()` completes. Gate any UI that needs `canWriteReports` on `await whoamiReady`. After login, reassign `whoamiReady = fetchWhoami().catch(() => {})` so the flag is re-evaluated with the new credentials.
- `localDateStr(d?)` returns a `YYYY-MM-DD` string using local date methods — never `toISOString()` for date-only values (UTC lag).
- **(2026-07-29)** Report action buttons (Perform/Cancel/Edit) are always visible for users with write access — they no longer hide/show as the request moves through states, only their `disabled` attribute changes, so the toolbar doesn't jump around. Perform + Cancel share one pill (`.action-group`), enabled until the request is performed or cancelled, then both lock together. Edit is disabled until performed, then enabled only while there's still an editable, unvalidated analysis (still hides entirely once nothing is left to edit — e.g. fully validated). Reset step at the top of each `fetchAndFillReport`/`refreshActionState` pass sets `disabled = true` (not `hidden = true`) so nothing is clickable during the fetch. Validate toggles are unaffected by this — they still hide/show based on report content. Disabled styling uses `--muted` text/border, not dimmed opacity (see CSS design system below).
- New icon glyphs must be added to `static/fontawesome.css` — the file is a curated subset, not the full FA bundle. Check before using any `fa-*` class.
- The profile tab's "Related Requests" panel (`renderPatientScheduleCard`), positioned between Personal Info and Scan Codes, reuses the Schedule tab's row markup — `buildTimelineRow(r, { isLast, timeLabel })` was extracted out of `renderSchedule()` for this. It's a **client-side filter of `scheduleEntries`, not a dedicated fetch**: it only shows entries already loaded by having visited the Schedule tab this session (matched by the patient's structured `family`+`given` name, not the schedule row's scraped display string — Hipocrate's own spacing/formatting differs between the two pages). It does not refresh if the Schedule tab is (re)loaded after the profile is already displayed — call `renderPatientScheduleCard(patientData)` again if that gap needs closing later.
- Its container carries `.timeline-compact` — an unconditional duplicate of the `@media (max-width: 700px)` narrow/stacked timeline-row layout (`static/styles.css`, right after that media query), since this panel is one ~360px column in the profile's masonry layout even on a wide desktop, and plain CSS can't combine a media-width condition with a descendant-selector condition in one rule. If the mobile timeline layout ever changes, update both blocks.
- **(2026-07-30)** `buildImagingCardHeader()`'s `**Examination:**` line prefers the card's own `.type-text` (set from the ServiceRequest, e.g. "CT Scan") and `.card-regions` (e.g. "abdomen") over the DiagnosticReport's `data.modality[0].display`, which comes back as a generic `"Other"` for many reports even when the exam is a plain CT/MRI — `data.modality` is now only a last-resort fallback, not the primary source.
- **(2026-08-19)** Schedule auto-refresh (`startScheduleAutoRefresh`/`scheduleNextAutoRefresh`) is a self-rescheduling `setTimeout` chain, not a fixed `setInterval`: it starts at 5 minutes and multiplies the interval by 1.2x after each tick, capped at 15 minutes, to ease off polling on schedules left open a long time. Clicking the manual refresh button (`refreshScheduleBtn`) resets the interval back to 5 minutes via `startScheduleAutoRefresh(true)` — but only if auto-refresh is currently running, so it's a no-op before login/first schedule load. Each tick calls `fetchScheduleFromInputs(true)`, which also re-warms the idle-prefetch cache (imaging/lab/epicrisis) for newly-appeared schedule entries.

## CSS design system

- `var(--radius-sm/md/lg/full)` — `var(--radius)` is **not defined**.
- `var(--font-size-xs/sm/base/lg/2xl/3xl/5xl)` / `var(--font-weight-normal/medium/semibold/bold)`.
- `var(--spacing-xs/sm/md/lg/xl/2xl)` — no hardcoded `px` or `rem`.
- `--header-height: 72px` for sticky nav `top` offset.
- Modality colours: `--mod-xr`, `--mod-ct`, `--mod-mr`, `--mod-us`, `--mod-fl` (not `--modality-*`).
- Action-button color semantics: Perform uses `--success`, Cancel/destructive uses `--danger`, disabled state uses `--muted` (text/border, not opacity).

## Dual API surface

- `/api/<resource>` → `HippoData` plain JSON; `?debug=page` returns raw Hipocrate HTML.
- `/fhir/<Resource>` → FHIR R4 JSON.
