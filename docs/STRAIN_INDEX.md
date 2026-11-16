# Strain index (the on-call radiology shift)

`strain.py`, computed per 10-minute point by `queuestats.compute()` and shown on the Schedule tab: the queue graph's dotted line, the hover readout (`strain NN`, tooltip = its parts) and the hero's Strain tile. Added 2026-11-12; rebuilt the same day from the owner's experience of on-call nights; widened on 2026-11-14 from the UPU ultrasounds to the whole on-call shift (X-ray, CT, RF, MRI and ward studies the team reports), with a summary per shift.

## What it is, and is not

A **relative 0–100 index of how difficult the on-call radiology shift is at a moment**: how adverse the working conditions of the on-call team are. It lets two moments, hours or shifts be compared; each shift also gets a few summary numbers (below).

It is **not**:
- a probability of missing a pathology, of a superficial read, or of anyone losing their temper. There are no outcomes (misses, addenda, discrepancies, complaints) to calibrate against, and nothing in the data measures temper;
- calibrated: every weight and reference below is an **assumption**, chosen to be plausible, matched to the owner's account of on-call nights, and kept in one place (the constants at the top of `strain.py`);
- a measure of a person. It describes the *system* (load, queue, work done, clock). Do not break it down per radiologist or use it to assess individuals.

Read it as "conditions known to raise the risk of errors, hurried reads and short tempers", nothing more.

## The facts it rests on (owner, 2026-11-12)

- One ultrasound runs from calling the patient (1–2 min), preparation, the scan, talking to the patient and discharge to the **written report**. Nothing else starts before the report (rare exceptions). So an exam's busy time is *PACS study start → report validation*.
- The **exam queue** (patients waiting for the radiologist) is the UPU ultrasounds only, not the wards' (14 radiologists share those in the day).
- On call there is usually a **senior and a junior**; the senior takes 20:00–02:00. A gap of 30 minutes or more in the senior's own UPU work, while the junior works, is rest (a 15–20 minute nap is possible). The junior's UPU work still counts toward the accumulated work: it stands for the senior's ward ultrasounds, CT and other duties, and for the nights they are alone.
- The on-call radiologist **also works the morning**: the duty block runs from one day's start to the next, 08:00 Monday-Friday and 09:00 Saturday and Sunday (owner, 2026-11-16). On call is weekdays from 14:00, weekends the whole block: Mon-Thu 18 h, Fri 19 h (to Saturday 09:00), Sat 24 h, Sun 23 h (to Monday 08:00).
- The strain at 03:00–05:00 after 40–50 ultrasounds is **very high even with a short queue**: it builds up over the duty, and an idle gap of 10 minutes is not rest.
- "Short exams with long spaces between them while a queue waits" is a sign of fatigue: getting rid of the patients fast.
- ~~X-rays and CT are not counted.~~ Since 2026-11-14 (owner) **every report the on-call team validates counts**: X-ray, CT, RF, MRI, from UPU or a ward. What is on-call work is told by **who validated it and when**, not by the requesting section.
- A **burst of arrivals** adds pressure over the next 1–2 hours.

## What the shift is made of (data of 6–12 Nov 2026)

Seven on-call blocks, 1695 imaging requests, validators pseudonymised:

| Requested on call, per day | UPU | ward |
|---|---|---|
| Ultrasound | 64 | 7 |
| X-ray | 53 | 6 |
| CT | 1.8 | 1.6 |
| MRI / RF | 0 / 0 | 1.2 / 0.3 |

- The on-call team was **two radiologists in 5 blocks, one in 2**. It validated **every UPU X-ray and UPU CT inside the block**, and the weekend's ward ultrasounds. Ward CT, MRI, RF and X-rays requested at night were mostly reported the next morning by the day staff: those are not the shift's work. Hence the rule by validator, not by section.
- The day staff leave 1–4 reports at 14:00–14:15: a team member needs `TEAM_MIN_REPORTS` (5) in the on-call hours.
- The senior (most reports 20:00–02:00) is the same person whether only ultrasounds or all reports are counted (7 of 7 blocks).
- Nothing records when a study is opened, only when its report is validated, to the minute. The gap to the same radiologist's previous report: **X-ray median 2 min** (48 % within a minute: read in batches; 76 % within 3), **CT median 22 min**. Exam → report: X-ray median 21 min (p90 61), CT 24 (p90 40).
- About 5 % of the X-rays are never reported (the row stays "active").

## Formula

Two parts, each 0..1:

```
index   = 100 · (1 − (1 − now) · (1 − fatigue))
now     = 0.35 · load + 0.25 · pressure + 0.20 · burst + 0.20 · rushing
fatigue = accumulated · (0.5 + 0.5 · sleepiness · engaged)
```

Either part alone raises the index; both together raise it more. With nothing done since 08:00 and nobody waiting it reads 0 at any hour. It stays high while the room is idle late in a long block: it describes the conditions the next patient meets, not the work of that minute.

## The parts

`clamp(v) = min(1, max(0, v))`. All parts are sent 0–100 as `strain_c` with every point, `now` and `fatigue` included.

### now: the moment's work

| Part | Weight | Definition |
|---|---|---|
| `load` | 0.35 | `clamp((ρ − 0.30) / 0.70)`, ρ the **work offered in the hour, in radiologist hours**: the UPU ultrasound requests × mean exam length, plus the reading time of the X-rays, CTs… done in that hour (`rho_read` in the series). 0 at 30 %, 1 at 100 % or more (more than one radiologist can do alone) |
| `pressure` | 0.25 | the worst of: people waiting for an ultrasound `L / L_ref`, their mean wait `W / W_ref`, the **longest wait** at that moment `/ (2 · W_ref)` (clinicians call about the patient waiting longest, not about the average); and of the **reading queue**: studies done and not reported `read_L / R_ref`, the oldest of them `/ (2 · O_ref)`. The references are the span's 90th percentile of the hourly values, never under 3 people / 45 min / 5 studies / 60 min (`strain_refs` in the response) |
| `burst` | 0.20 | the worst recent burst of requests: for every 30-minute window ending at a request in the last 2 hours, the requests in it beyond what the room clears in half an hour (capacity × 0.5 h, capacity = 1 / mean exam length, 4/h when unknown), over 3. Felt fully for 1 hour after the window, fading linearly to 0 at 2 hours. Steady arrivals at the same ρ read 0 |
| `rushing` | 0.20 | `shorter × clamp(idle_waiting / 0.25)`: both needed. Fast exams back to back are efficiency; idle gaps alone may be a CT being read |

- **`shorter`**: each exam's length over the median length of exams **of the same regions** (`abdomen+pelvis`, `hip`…, from the report page's studies, at least 3 of a kind, else all exams). The median of the hour's ratios: 1 = usual, 0.5 = half as long. `clamp((1 − median) / 0.5)`; 0 with fewer than 3 exams in the hour.
- **`idle_waiting`**: the share of the hour with someone waiting and the room idle, the first 5 minutes of each idle gap left out (calling and preparing the next patient). The room is not idle while the on-call team reads an X-ray or a CT.
- `burst` and `rushing` stay signals of the ultrasound queue.

### The reading queue

A study is in it from the moment it is done (`performed_at`) until its report is validated:
- every **UPU** read (X-ray, CT…): still open when performed and not reported; out when the row has ended with no cached report time (unknown), or was never performed;
- a **ward** read only if an on-call team member validated it in the on-call hours, and from the handover at the earliest; one left for the day staff never enters;
- an open read stops counting after its modality's usual wait (95th percentile, 2–24 h, as for the other stages); seen later (a past day), a read still unreported past that was never going to be read and **never waited** (`coverage.stale.read`).

In the response: `current.reading` (λ, X, L, W of the last hour, `now`, `oldest`, the span's), `read_L` and `read_oldest` per point.

### fatigue: what the duty has cost

- **`accumulated`**: the work done on call, as an integral:
  - busy time adds up: **the on-call team's work in every modality**. The UPU ultrasound exams, senior's and junior's (PACS start → report; with no measured end, the median exam length cut at the next start; with no PACS start at all, the median length ending at the report, else at the performed time: `work_intervals()`), and **every other report a team member validates** (`read_work()`, below);
  - an idle gap **under 30 minutes is not rest**: it changes nothing;
  - a gap of 30 minutes or more **in the senior's own exams and reports** is rest: for its whole length the accumulated work decays with a **half-life of 3.5 hours** (a 2.5-hour rest takes off about 40 %; 8 h until 2026-11-16, when a quiet 03:00-05:00 barely lowered the strain);
  - read on a saturating scale, `1 − 2^(−hours / 3.25)`: 3.25 busy hours = 50 %, 6.5 h = 75 %, 9.75 h = 88 %. Real ultrasound exams last 7–9 minutes (call to written report); with the night's X-rays and CTs the owner's 40–50 ultrasounds are about 9 busy hours and read about 85 %, as they did on the 2.5 h scale before the reads were counted. It nears 1 and never clips, so a heavy night still differs from a very heavy one.

#### How long a read takes (`read_work()`)

Per radiologist, in the order of their reports (their ultrasound exams included): a read **ends at its validation** and starts at the latest of
- its typical length before: `READ_TYPICAL` × the request's validated studies (X-ray 3 min, CT 25, RF 15, MRI 30; a ward ultrasound the median measured UPU exam). Assumptions;
- the end of that radiologist's previous report: X-rays read in a batch cost what they took;
- the moment the images existed (`performed_at`);

and never lasts under `READ_MIN` (1 minute: several reports validated the same minute). A limit: one radiologist's work cannot exceed the clock, so the same reports done by one person squeezed between ultrasounds count fewer minutes than done by two in parallel.
- **`sleepiness`** = `0.6 · circadian(t) + 0.4 · clamp(hours since the block's start / 24)`:
  - **circadian(t)**: an *assumed* curve inspired by the two-process model's process C, linear between `0:00 .65 · 2:00 .85 · 4:00 1.0 · 6:00 .85 · 8:00 .40 · 10:00 .15 · 12:00 .20 · 14:00 .40 · 15:00 .40 · 16:00 .25 · 18:00 .10 · 20:00 .20 · 22:00 .45 · 24:00 .65`. Deepest 02:00–06:00, a smaller dip after lunch;
  - **hours on duty**: since the block's start (08:00 weekdays, 09:00 weekends; before it, since the day before's). Holidays are not known.
- **`engaged`** (2026-11-16, owner: a quiet 03:00-05:00 is not strain): sleepiness weighs only near work. 1 while the team works and for `ENGAGED_HOLD` (60 min) after their last exam or report, fading linearly to 0 at `ENGAGED_FADE` (120 min); 0 before any work. A long quiet stretch leaves only the accumulated work at the fatigue floor; a short break after heavy work keeps the night's sleepiness.
- The `0.5 +` floor: fully rested, the accumulated work counts half; at the deepest of the night after a long block, fully.

### Whose work, whose rest: the on-call team and the senior

Most on-call blocks have a **senior and a junior** radiologist; some have one (owner, 2026-11-12; 2 of 7 in the data above). The senior usually takes the busiest hours, 20:00–02:00, while the junior covers the UPU the rest of the time; the senior then does ward ultrasounds, CT and other duties, and may nap 15–20 minutes if the junior does not call.

- **The team** of a duty block (`on_call_team()`): whoever validated `TEAM_MIN_REPORTS` (5) reports or more, of any modality and section, in its on-call hours (weekdays from 14:00, weekends from 08:00, to 08:00). Until someone has that many, whoever validated one later than `TEAM_GRACE` (30 min) after the handover, which leaves out the day staff's last reports.
- **The senior** (`on_call_radiologist()`): the team member who validated most reports, of any modality, between 20:00 and 02:00. Before 20:00, the one with most in the on-call hours so far. Alone on call, that is the one radiologist.
- **What accumulates**: the team's work from the handover: every UPU ultrasound exam since then and every other report a team member validated. The day staff's work before 14:00 on weekdays is left out, as is a ward study the team did not report.
- **What is rest**: an idle gap of 30 minutes or more in **the senior's own** exams and reports, between two of them or since their last one; the junior may be working meanwhile. Reading X-rays or a CT is no longer mistaken for rest. During rest the accumulated work decays (half-life 3.5 h); the junior's work in it still adds up.
- Before anyone has validated a report on call (a weekday morning seen live), the team's own gaps are the rest, and the point says so (`on_call_known: false`, in the tooltip).
- **Names never leave** `queuestats.compute()`: not returned, logged or stored. The response has only counts.
- `burst` and `rushing` stay the ultrasound queue's, whoever serves it.

**Open question (2026-11-14)**: the junior's UPU work was counted because it *stood for* the senior's ward, CT and other duties, which were not measured (owner, 2026-11-12). They are measured now, so a team block counts two people's minutes where a solo block counts one's. On the seven real blocks the two solo ones read lowest (table below), partly because they were also the quietest by queue. Whether the accumulated work should become the senior's own only is the owner's call.

## The shift summary

`shifts[]` in the response, one entry per duty block of the span (`shift_summary()`), shown in the hero subtitle (all of them in its tooltip):

| Field | Meaning |
|---|---|
| `from`, `to` | the on-call hours: weekdays 14:00, weekends 09:00, to the next block's start (08:00 weekdays, 09:00 weekends) |
| `peak`, `mean` | of the index over those hours |
| `hours_high` | hours with the index at 65 or more (`SHIFT_HIGH`) |
| `reports` | the team's reports: `us` (UPU ultrasound exams), `xr`, `ct`, `rf`, `mr` |
| `ward` | how many of the reads came from a ward |
| `radiologists` | the team's size (1 or 2) |
| `complete` | the whole shift lies in the span analysed |

No single figure is declared "the" difficulty of a shift: the mean says how hard it was on average, the peak and the hours at 65+ how bad and how long its worst part.

## What it gives

Computed with `strain.score()`; ultrasound exams of 9 minutes spread evenly from 14:00, requests arriving steadily at 4 an hour unless a burst is named (6 requests in 15 minutes), capacity 6.5 exams an hour. Reads add their minutes: 40 X-rays read at 2 minutes and 2 CTs at 25 are 2.2 busy hours more.

| Moment | Index | now | burst | accumulated | sleepiness | fatigue |
|---|---|---|---|---|---|---|
| 16:00, 8 done since 14:00, 1 waiting | **30** | 18 | 0 | 23 | 28 | 14 |
| 18:00, 15 done, 5 waiting | **66** | 55 | 0 | 38 | 23 | 23 |
| 21:00, 20 done, 6 arrived 20:30-20:45, 4 waiting | **82** | 73 | 92 | 47 | 41 | 33 |
| 22:00, the same burst an hour on, 2 waiting | **67** | 46 | 69 | 51 | 50 | 38 |
| 00:00, 30 done, 2 waiting | **67** | 32 | 0 | 62 | 66 | 51 |
| 04:00, 20 done (quiet night), 2 waiting | **51** | 27 | 0 | 34 | 93 | 33 |
| 04:00, 45 done, nobody waiting | **74** | 0 | 0 | 76 | 93 | 74 |
| 04:00, 45 done, 2 waiting | **81** | 27 | 0 | 76 | 93 | 74 |
| 04:00, 45 done + 40 X-rays + 2 CT, 2 waiting | **87** | 27 | 0 | 85 | 93 | 82 |
| 04:00, 45 done, 5 waiting | **87** | 50 | 0 | 76 | 93 | 74 |
| 04:00, 45 done, rested 01:00-03:30, 2 waiting | **76** | 27 | 0 | 69 | 93 | 67 |
| 04:00, 45 done, short exams + idle while 5 wait | **92** | 70 | 0 | 76 | 93 | 74 |
| 07:30, 55 done, 3 waiting | **82** | 40 | 0 | 83 | 70 | 70 |

The quiet night reads lower than its 20 exams suggest: spread over 14 hours they leave gaps over 30 minutes, which count as rest.

## How to read the numbers

- Readout colours: below 40 muted, 40–64 orange, 65 and over red. Display thresholds, not risk classes.
- Meaningful for comparing times and days of *this* queue; not comparable with another department or tool.
- The index is about conditions, not a person's performance: the validator only decides whose work accumulates. Do not use it to compare radiologists.
- `load` is in radiologist hours: 100 % is one radiologist's full hour, whoever is on call.
- `pressure` is judged against the span shown, so the same moment reads differently in the 12 h, 24 h and multi-day views. The other parts do not depend on the span.
- Coverage limits: `accumulated`, `rushing` and the measured ρ need PACS exam starts (coverage in the hero subtitle); `shorter` by region needs the report pages cached (else all exams are one kind).
- X-ray, CT and the other reads need their report pages cached (`coverage.read_times`; the Schedule prefetch warms them for the rows shown). A read's length is an estimate (above), never a measurement.

## Seen on real data (2026-11-14)

Seven on-call days, 08:00 → 08:00, through `GET /api/schedule/queue` (aggregates only). The index before = ultrasound only, 2.5 h scale (`340b95d`).

| Day | Team | On-call reports: US / X-ray / CT (from wards) | index 16:00 / 20:00 / 00:00 / 02:00 / 04:00 / 06:00 | before | peak · mean · hours at 65+ |
|---|---|---|---|---|---|
| Fri 6 Nov | 2 | 59 / 48 / 3 (5) | 28 / 66 / 85 / 76 / 75 / 69 | 23 / 46 / 74 / 70 / 65 / 60 | 90 · 68 · 12.7 |
| Sat 7 Nov | 2 | 92 / 92 / 1 (15) | 66 / 62 / 75 / 85 / 82 / 75 | 62 / 55 / 72 / 84 / 80 / 72 | 91 · 64 · 15.5 |
| Sun 8 Nov | 2 | 80 / 48 / 4 (13) | 65 / 80 / 85 / 84 / 86 / 76 | 49 / 58 / 69 / 74 / 72 / 63 | 90 · 71 · 18.8 |
| Mon 9 Nov | 1 | 56 / 64 / 2 (6) | 30 / 52 / 63 / 66 / 62 / 60 | 27 / 32 / 55 / 55 / 50 / 52 | 70 · 52 · 2.2 |
| Tue 10 Nov | 2 | 84 / 48 / 2 (1) | 72 / 65 / 91 / 90 / 95 / 86 | 69 / 64 / 90 / 89 / 95 / 87 | 97 · 80 · 16.3 |
| Wed 11 Nov | 2 | 67 / 62 / 4 (10) | 70 / 62 / 83 / 85 / 81 / 80 | 63 / 60 / 81 / 84 / 78 / 73 | 93 · 75 · 14.7 |
| Thu 12 Nov | 1 | 62 / 53 / 1 (8) | 32 / 68 / 48 / 56 / 50 / 41 | 36 / 58 / 40 / 48 / 31 / 29 | 77 · 51 · 2.0 |

- The weekday labels of the earlier version of this table were a day off (10 Nov 2026 is a Tuesday).
- The heaviest night (Tue 10) reads as before, 90–95 between 00:00 and 04:00: the scale (3.25 h) was set for that. Nights with many X-rays against few ultrasounds (Fri 6, Sun 8, Mon 9) read 10–15 higher than before.
- The two **solo** blocks read lowest. They were also the quietest by queue (Thu 12: almost no ultrasound after midnight), and one person's reports squeezed between ultrasounds count fewer minutes than two people's in parallel: see the open question above.
- Thu 12, 04:00–05:00: X-rays done around 02:30 were reported near 05:30 (the oldest unread 148 min): the reading queue's pressure, real.
- A cold call reads about 2.5 times more cached pages than before (five listings, all the reports); warm, the computation takes about 0.2 s.

Notes kept from the first three days (2026-11-12, ultrasound only):

- The busy night of 10 Nov reads 89–95 between 02:00 and 04:00, the owner's experience; the quieter 11 Nov 73–80. (Counting only the senior's own exams, before the team model, they read 82–90 and 55–67.)
- On all three days **the on-call radiologist validated no UPU ultrasound before 14:00**: their morning is other work, so their accumulated UPU work starts at 14:00 (the duty clock, for sleepiness, still at 08:00).
- With the senior's own exams alone, the accumulated work fell in the evening while the queue was long (Monday 18:00 → 22:00): the junior was doing the UPU. Counting the team's work, it keeps rising until the senior's real rests.
- Today's reports appear only once their pages are cached: until then the senior is not known and the point says so.
- Real exams (call to written report) last 7–9 minutes, hence `ACCUM_HALF_FULL_H` = 2.5 h then (3.25 h since the reads count).
- 174 exams of 9 minutes are 26 hours of work in 24: in the day shift more than one radiologist does UPU ultrasounds. Hence `accumulated` counts only the on-call radiologist's exams (by validator, above).
- Matching exam starts needs each patient's CNP from cached pages; older days are not cached (8 Nov: 4 %). There `accumulated` rests on the report times (`work_intervals()`), `idle_waiting` is unreliable and the index reads low. Coverage is in the hero subtitle: below about 75 % read the strain with care.
- Weekday mornings had 10–16 other ultrasound studies an hour (other rooms, other radiologists): the reason ward studies were first gated, then left out.

## History

1. **First version** (`cf85653`): a weighted sum, with sleepiness a 0.30 term: an empty room read about 25 at 04:00, mostly a clock curve.
2. **Fatigue as a multiplier** (`c0f002c`): `work × (0.5 + 0.5 · sleepiness)`, with `no_break` (back-to-back minutes, reset by any 10-minute gap). The owner's 04:00 case (45 done, 5 waiting) read 54, and 38 after a 15-minute pause: nothing remembered the night's work.
3. **A decaying integral since 14:00** (`10bdba8`): fixed the memory, but decayed during work too, and the block started at 14:00.
4. **Rest-only decay** (`2ca90d7`): the duty block starts at 08:00; only a rest of 30 minutes or more decays the work; a saturating scale; `shorter` by exam regions; the longest wait in `pressure`; calling time left out of `idle_waiting`; ward studies counted at every hour.
5. **Bursts** (`e6419e2`): bursts of arrivals, felt over the next 1–2 hours (`burst`).
6. **After the first real data** (`b77e9f3`): ward studies on call only, an unmatched UPU study no longer counted as ward work, UPU exams without a PACS start kept in `accumulated`.
7. **The on-call radiologist's own exams** (`e21e61e`): ward studies left out entirely; the accumulated work only the on-call radiologist's UPU exams, by validator; half full at 2.5 busy hours (real exams are 7–9 minutes, not 12).
8. **The team** (`340b95d`): the senior (most reports 20:00–02:00) and the team: the team's UPU work from the start of on-call accumulates, the senior's own gaps are the rest.
9. **The whole shift** (2026-11-14): X-ray, CT, RF, MRI and ward studies count when an on-call team member validates them in the on-call hours (the team: 5 reports or more); a read's length is the gap since that radiologist's previous report, capped by a typical length; a reading queue (exam → report) joins `pressure`; `load` is the work offered in radiologist hours; `ACCUM_HALF_FULL_H` 2.5 → 3.25 h; a summary per shift (`shifts[]`).

## Changing it

All tunables are constants at the top of `strain.py`:

| Constant | Value | Meaning |
|---|---|---|
| `NOW_WEIGHTS` | 0.35 / 0.25 / 0.20 / 0.20 | load / pressure / burst / rushing (sum to 1, tested) |
| `LOAD_FLOOR` | 0.30 | utilisation that counts as no load |
| `QUEUE_REF`, `WAIT_REF_MIN` | 3, 45 min | the floors of the span references |
| `READ_QUEUE_REF`, `READ_OLDEST_REF` | 5, 60 min | the same for the reading queue: studies unread, their usual longest wait |
| `OLDEST_FACTOR` | 2 | the longest wait (and the oldest unread study) is full at twice its reference |
| `SHORT_REF`, `SHORT_MIN_SAMPLES` | 0.5, 3 | half the usual length = 1; exams needed in the hour |
| `BURST_SPAN`, `BURST_REF` | 30 min, 3 | arrivals counted together; patients beyond capacity = 1 |
| `BURST_HOLD`, `BURST_FADE` | 1 h, 2 h | felt fully, then gone |
| `CAPACITY_DEFAULT_H` | 4 | exams per hour when the mean length is unknown |
| `IDLE_REF`, `CALL_ALLOWANCE` | 0.25, 5 min | a quarter of the hour idle while people wait = 1; calling is not idle |
| `REST_MIN` | 30 min | a shorter idle gap is not rest |
| `ACCUM_HALF_LIFE_H` | 3.5 h | decay of the accumulated work during rest |
| `ACCUM_HALF_FULL_H` | 3.25 h | busy hours that make `accumulated` half full |
| `ENGAGED_HOLD`, `ENGAGED_FADE` | 60, 120 min | sleepiness weighs fully this long after the last work, gone at the second |
| `FATIGUE_FLOOR` | 0.5 | share of the accumulated work counted fully rested |
| `DUTY_START_HOUR`, `WEEKEND_START_HOUR`, `ON_CALL_HOUR`, `DUTY_REF_H` | 08:00, 09:00, 14:00, 24 h | the duty block (weekday, weekend start), weekday on call |
| `CIRCADIAN` | see above | the assumed curve |

In `queuestats.py`: `REGION_MIN_SAMPLES` (3) sets how many exams of a kind give that kind its own median; `READ_TYPICAL` (X-ray 3, CT 25, RF 15, MRI 30 min per study) and `READ_MIN` (1 min) a read's length; `TEAM_MIN_REPORTS` (5) and `TEAM_GRACE` (30 min) who is on call; `SHIFT_HIGH` (65) the summary's `hours_high`; `SCOPE_LABS` the laboratories fetched. Tests: `python3 runtests.py strain` and `python3 runtests.py queuestats`. The table above is reproduced by scoring `strain.Moment`s by hand.

## Validating it (not done)

A calibration needs outcomes, which do not exist here. Defensible next steps:
- a *retrospective check of the proxies*: do report length or the share of "normal" template reports vary with the index, the hour and the accumulated work?
- **a sensitivity test**: score a month with many random weight sets; if the hours and days keep their ranking, the exact weights matter little;
- much slower, a link to follow-up findings (a CT or surgery within 72 h that contradicts the ultrasound).

Not modelled yet: night wake-ups (work resuming after a long quiet, broken sleep), triage colour, consecutive duties (needs the radiology roster: a count, never a name).

## References to check before relying on them

Quoted from memory, not verified here: Borbély, *a two process model of sleep regulation* (1982); Folkard & Tucker, *Shift work, safety and productivity* (2003: roughly 1.3× the day risk at night, rising over consecutive nights and with long shifts); the radiology literature on workload, fatigue and interpretive error (e.g. studies of error rate against shift length and volume).
