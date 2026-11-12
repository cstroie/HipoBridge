# Strain index (UPU ultrasound)

`strain.py`, shown on the Schedule tab's queue graph (dotted line) and in its hover readout (`strain NN`, tooltip = components). Added 2026-11-12.

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

Each is clamped to 0..1 (`c`). `clamp(v) = min(1, max(0, v))`. Four describe the **work** and are weighted:

| Component | Weight | Definition |
|---|---|---|
| `load` | 0.30 | `clamp((ρ − 0.30) / 0.70)`: 0 at 30 % utilisation, 1 at 100 % or more (ward studies included) |
| `pressure` | 0.20 | `max(clamp(L / L_ref), clamp(W / W_ref))`: people waiting, by count or by how long. The references are this span's 90th percentile of the hourly L and W, never under 3 waiting / 45 min (`strain_refs` in the response) |
| `no_break` | 0.35 | minutes of back-to-back work ending at the point, `/ 4 h`, UPU exams and ward studies alike. Work chained with idle gaps under 10 min counts as continuous; a gap of 10 min or more is a break (the run restarts); it is 0 when the last study ended more than 10 min ago |
| `rushing` | 0.15 | `clamp((median_span − median_hour) / (0.5 · median_span))`: the UPU exams that ended in the last hour are much shorter than the span's median (people speed up under load). 0 with fewer than 3 exams in the hour |

The fifth, **`sleepiness`** = `0.6 · circadian(t) + 0.4 · clamp(hours on duty / 24)`, has no weight of its own: it **scales** the work.

`index = round(100 · work · (0.5 + 0.5 · sleepiness))`, `work = Σ weight · component`.

So an empty room reads 0 at any hour (there is nothing to get wrong), and the same work weighs up to twice as much at 04:00 after a long block as fully rested. Until 2026-11-12 sleepiness was a 0.30 additive term, which made the index mostly a clock curve: about 25 at 04:00 with nobody waiting. `FATIGUE_FLOOR` (0.5) is the share counted fully rested, an assumption like the weights.

`no_break` is weighted up on purpose (2026-11-12): unbroken work also stands in, a little, for accumulated strain, which the index otherwise does not model (a leaky accumulator was considered and left for later).

The five components are sent (0–100) as `strain_c` with every point, with `ward` (ward studies started in the hour) and `rho_room`.

### Sleepiness

Inspired by the two-process model of sleep regulation (a homeostatic pressure that rises with time awake, plus a circadian rhythm), reduced to what can be known here:

- **circadian(t)**: an *assumed* curve, linearly interpolated between these (hour, value) nodes: `0:00 .65 · 2:00 .85 · 4:00 1.0 · 6:00 .85 · 8:00 .40 · 10:00 .15 · 12:00 .20 · 14:00 .40 · 15:00 .40 · 16:00 .25 · 18:00 .10 · 20:00 .20 · 22:00 .45 · 24:00 .65`. Deepest between 02:00 and 06:00, a smaller dip after lunch, best mid-morning and early evening.
- **duty hours**: hours since the duty block began, as a stand-in for time awake. Blocks (`duty_start()`): weekdays, day shift from 08:00 and on-call from 14:00 to 08:00; Saturdays and Sundays from 08:00 to 08:00; before 08:00 a point belongs to the previous day's block. **Holidays are not known** and are treated as ordinary days.

The duty clock is only a proxy: someone awake long before the shift, or resting during a quiet night, differs from it.

## Worked example

Yesterday 01:00: ρ 0.57, L 2.46, W 42 min, 4 h or more of unbroken work, 11 h on duty (since 14:00), circadian 0.75.
`load` 39 · `pressure` 94 · `no_break` 100 · `rushing` 0 · `sleepiness` 63
→ work = 0.30·0.39 + 0.20·0.94 + 0.35·1 + 0.15·0 = 0.655; × (0.5 + 0.5·0.63) = 0.815 → 53.4 → **53** (66 under the earlier additive form). With the span's references `pressure` would read lower.

## How to read the numbers

- Rough bands used for the readout colour: below 40 muted, 40–64 orange, 65 and over red. They are display thresholds, not risk classes. Under the multiplicative form a rested daytime peak tops out near 65, so red is in practice night-time or long-block work; the bands were not re-tuned.
- It is meaningful for comparing times and days of *this* queue. It is not comparable with another department or another tool.
- Coverage limits apply: `no_break`, `rushing` and the measured ρ need PACS exam starts (see coverage in the hero subtitle); where there are none they fall back or read 0. Without the PACS day list there are no ward studies, and the radiologist's load is understated.
- The ward studies are assumed to be the UPU radiologist's work **inside the on-call block only** (weekdays 14:00→08:00, weekends; `queuestats.on_call()`): in the weekday day shift another room or radiologist may scan in parallel. This is an assumption, **not confirmed** by the owner (who confirmed only that one UPU exam runs from call to written report with nothing starting in between). A ward study's length is not measured (its report time is not read): the UPU median, cut at the next start.
- `pressure` saturated in the first live view (2026-11-12: waits of 30–60 min are normal for this queue), hence the span-relative references. The cost: `pressure` compares a moment with its own span, so it is less comparable across days than the other components; the floors keep a quiet day's small queue from reading as full pressure.
- The duty clock restarts at 14:00 on weekdays. If the on-call radiologist also worked that morning, time on duty and sleepiness are understated after 14:00 (not confirmed; `duty_start()`).

## Changing it

All tunables are module constants in `strain.py`: `WEIGHTS` (the work components, must sum to 1, tested), `FATIGUE_FLOOR`, `LOAD_FLOOR`, `QUEUE_REF`, `WAIT_REF_MIN` (the floors of the span references), `BREAK_GAP`, `NO_BREAK_REF`, `DUTY_REF_H`, `RUSH_*`, `CIRCADIAN`. Tests: `python3 runtests.py strain`.

## Validating it (not done)

A calibration needs outcomes, which do not exist here. A defensible next step would be a *retrospective check of the proxies* (do exam duration, report length or the share of "normal" template reports vary with the hour and the load?), and, much slower, a link to follow-up findings (a CT or surgery within 72 h that contradicts the ultrasound). Neither is built.

## References to check before relying on them

Quoted from memory, not verified here: Borbély, *a two process model of sleep regulation* (1982); Folkard & Tucker, *Shift work, safety and productivity* (2003: roughly 1.3× the day risk at night, rising over consecutive nights and with long shifts); the radiology literature on workload, fatigue and interpretive error (e.g. studies of error rate against shift length and volume).
