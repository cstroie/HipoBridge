# Strain index (UPU ultrasound)

`strain.py`, shown on the Schedule tab's queue graph (dotted line) and in its hover readout (`strain NN`, tooltip = components) and in the hero's Strain tile. Added 2026-11-12.

## What it is, and is not

A **relative 0–100 index of how adverse the working conditions of the UPU ultrasound radiologist are at a moment**, one value per 10-minute point. It lets two moments, hours or days be compared.

It is **not**:
- a probability of missing a pathology, of a superficial read, or of anyone losing their temper. There are no outcomes (misses, addenda, discrepancies, complaints) to calibrate against, and nothing in the data measures temper;
- calibrated: the weights and reference values below are **assumptions**, chosen to be plausible and kept in one place (`strain.WEIGHTS` and the constants above it);
- a measure of a person. It describes the *system* (load, queue, clock). Do not break it down per radiologist or use it to assess individuals.

Read it as "conditions known to raise the risk of errors, hurried reads and short tempers", nothing more.

## Inputs

All come from the queue analysis (`queuestats.py`), no new data source:

| Signal | From |
|---|---|
| ρ of the hour (λ / μ) | UPU requests made in the hour **plus the ward ultrasound studies started in it** over the capacity (1 / mean UPU exam duration; the demonstrated-capacity guess with fewer than 5 exams). Sent as `rho_room`; `rho` stays the UPU queue's |
| L, W of the hour | mean number waiting and mean wait (request → exam start) |
| UPU exam intervals (start, end) | PACS study start → written report, capped by the next study's start (`service_samples()`). An exam is call, preparation, scan, talk, discharge and the written report, one at a time (owner, 2026-11-12); over 60 min is a late report, no sample |
| ward studies | the day's other ultrasound studies from the PACS (`PacsChecker.studies_for_day()`, any patient, not matched to a UPU request), started on call only: each lasts the UPU median, cut at the next start (`ward_intervals()`) |
| clock | the point's time and the duty block it falls in |
| clock | the point's time and the duty block it falls in |

## Components

Each is clamped to 0..1 (`c`). `clamp(v) = min(1, max(0, v))`. The index has two parts (2026-11-12, from the owner's experience: at 03:00–05:00, after 40–50 ultrasounds since the duty began, the strain is very high even with a short queue).

**now**, the moment's work, weighted:

| Component | Weight | Definition |
|---|---|---|
| `load` | 0.45 | `clamp((ρ − 0.30) / 0.70)`: 0 at 30 % utilisation, 1 at 100 % or more (ward studies included) |
| `pressure` | 0.30 | `max(clamp(L / L_ref), clamp(W / W_ref))`: people waiting, by count or by how long. The references are this span's 90th percentile of the hourly L and W, never under 3 waiting / 45 min (`strain_refs` in the response) |
| `rushing` | 0.25 | "get rid of them fast" (owner): `shorter × clamp(idle_waiting / 0.25)`. `shorter` = `clamp((median_span − median_hour) / (0.5 · median_span))`, the UPU exams that ended in the last hour much shorter than the span's median (0 with fewer than 3); `idle_waiting` = the share of the hour with someone waiting and the room idle. Both are needed: fast exams back to back are efficiency, idle gaps alone may be other work |

**fatigue** = `accumulated × (0.5 + 0.5 · sleepiness)`:

- **`accumulated`**: the integral of the work done since the duty block began, every busy minute (UPU exams, ward studies on call, UPU exams with no measured end at the typical length) weighted `2^(−age / 8 h)`, so rest on duty recovers slowly and a break does not reset it. 6 h of this decayed busy time = 1: about 45 exams of 12 min spread from 14:00 to 04:00. Computed exactly per interval (`accumulated_hours()`).
- **`sleepiness`** below.

`index = round(100 · (1 − (1 − now) · (1 − fatigue)))`: either part alone raises the index, both together raise it more. Nothing done since the block began and nobody waiting reads 0.

History: until 2026-11-12 the index was a weighted sum with sleepiness as a 0.30 term (a clock curve: about 25 at 04:00 in an empty room), then briefly `work × (0.5 + 0.5 · sleepiness)` with a `no_break` term (back-to-back minutes, reset by any 10-minute gap). Both read only 54 for the owner's 04:00 case (45 done, 5 waiting), and 38 after a 15-minute pause: nothing remembered the night's work.

All parts are sent (0–100) as `strain_c` with every point (`now` and `fatigue` too), with `ward`, `rho_room` and `idle_waiting`.

### Sleepiness

Inspired by the two-process model of sleep regulation (a homeostatic pressure that rises with time awake, plus a circadian rhythm), reduced to what can be known here:

- **circadian(t)**: an *assumed* curve, linearly interpolated between these (hour, value) nodes: `0:00 .65 · 2:00 .85 · 4:00 1.0 · 6:00 .85 · 8:00 .40 · 10:00 .15 · 12:00 .20 · 14:00 .40 · 15:00 .40 · 16:00 .25 · 18:00 .10 · 20:00 .20 · 22:00 .45 · 24:00 .65`. Deepest between 02:00 and 06:00, a smaller dip after lunch, best mid-morning and early evening.
- **duty hours**: hours since the duty block began, as a stand-in for time awake. Blocks (`duty_start()`): weekdays, day shift from 08:00 and on-call from 14:00 to 08:00; Saturdays and Sundays from 08:00 to 08:00; before 08:00 a point belongs to the previous day's block. **Holidays are not known** and are treated as ordinary days.

The duty clock is only a proxy: someone awake long before the shift, or resting during a quiet night, differs from it.

## What it gives

Computed with `strain.strain()`, exams of 12 min spread evenly since the duty began (Wednesday; on-call since Tuesday 14:00):

| Moment | Index | now | accumulated | sleepiness | fatigue |
|---|---|---|---|---|---|
| 10:00, 8 done since 08:00, 1 waiting | 33 | 23 | 24 | 12 | 14 |
| 12:00, 20 done since 08:00, 5 waiting | 79 | 69 | 56 | 19 | 33 |
| 20:00, 20 done since 14:00, 2 waiting | 58 | 39 | 52 | 22 | 32 |
| 00:00, 32 done, 2 waiting | 73 | 39 | 71 | 56 | 55 |
| 04:00, 20 done (quiet night), 2 waiting | 56 | 33 | 38 | 83 | 35 |
| 04:00, 45 done, nobody waiting | 79 | 0 | 86 | 83 | 79 |
| 04:00, 45 done, 5 waiting | 92 | 62 | 86 | 83 | 79 |
| 04:00, 45 done, the last 45 min a pause | 76 | 0 | 83 | 83 | 76 |
| 07:30, 55 done, 3 waiting | 87 | 49 | 94 | 60 | 75 |

## How to read the numbers

- Rough bands used for the readout colour: below 40 muted, 40–64 orange, 65 and over red. They are display thresholds, not risk classes.
- The index stays high while the room is idle late in a long block: it describes the conditions the next patient meets, not the work of that minute.
- It is meaningful for comparing times and days of *this* queue. It is not comparable with another department or another tool.
- Coverage limits apply: `accumulated`, `rushing` and the measured ρ need PACS exam starts (see coverage in the hero subtitle); where there are none they fall back or read 0. Without the PACS day list there are no ward studies, and the radiologist's load is understated.
- X-rays and CT read by the same radiologist are not counted; there are usually two radiologists, which the owner considers compensates. Gaps spent reading a CT can still read as `idle_waiting`; `rushing` needs short exams as well, which limits that.
- The ward studies are assumed to be the UPU radiologist's work **inside the on-call block only** (weekdays 14:00→08:00, weekends; `queuestats.on_call()`): in the weekday day shift another room or radiologist may scan in parallel. This is an assumption, **not confirmed** by the owner (who confirmed only that one UPU exam runs from call to written report with nothing starting in between). A ward study's length is not measured (its report time is not read): the UPU median, cut at the next start.
- `pressure` saturated in the first live view (2026-11-12: waits of 30–60 min are normal for this queue), hence the span-relative references. The cost: `pressure` compares a moment with its own span, so it is less comparable across days than the other components; the floors keep a quiet day's small queue from reading as full pressure.
- The duty clock restarts at 14:00 on weekdays, and `accumulated` with it. If the on-call radiologist also worked that morning, both are understated after 14:00 (not confirmed; `duty_start()`).

## Changing it

All tunables are module constants in `strain.py`: `WEIGHTS` (the moment's components, must sum to 1, tested), `FATIGUE_FLOOR`, `ACCUM_HALF_LIFE_H`, `ACCUM_REF_H`, `IDLE_REF`, `LOAD_FLOOR`, `QUEUE_REF`, `WAIT_REF_MIN` (the floors of the span references), `DUTY_REF_H`, `RUSH_*`, `CIRCADIAN`. Tests: `python3 runtests.py strain`.

## Validating it (not done)

A calibration needs outcomes, which do not exist here. A defensible next step would be a *retrospective check of the proxies* (do exam duration, report length or the share of "normal" template reports vary with the hour and the load?), and, much slower, a link to follow-up findings (a CT or surgery within 72 h that contradicts the ultrasound). Neither is built.

## References to check before relying on them

Quoted from memory, not verified here: Borbély, *a two process model of sleep regulation* (1982); Folkard & Tucker, *Shift work, safety and productivity* (2003: roughly 1.3× the day risk at night, rising over consecutive nights and with long shifts); the radiology literature on workload, fatigue and interpretive error (e.g. studies of error rate against shift length and volume).
