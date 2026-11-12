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
| ρ of the hour (λ / μ) | requests made in the hour over the measured capacity (1 / mean exam duration; the demonstrated-capacity guess with fewer than 5 exams) |
| L, W of the hour | mean number waiting and mean wait (request → exam start) |
| exam intervals (start, end) | PACS study start → written report, capped by the next exam's start (`service_samples()`; the radiologist's busy time, the report being part of it) |
| clock | the point's time and the duty block it falls in |

## Components

Each is clamped to 0..1 (`c`), then weighted. `clamp(v) = min(1, max(0, v))`.

| Component | Weight | Definition |
|---|---|---|
| `load` | 0.20 | `clamp((ρ − 0.30) / 0.70)`: 0 at 30 % utilisation, 1 at 100 % or more |
| `pressure` | 0.15 | `max(clamp(L / 3), clamp(W / 45 min))`: people waiting, by count or by how long |
| `no_break` | 0.25 | minutes of back-to-back work ending at the point, `/ 4 h`. Exams chained with idle gaps under 10 min count as continuous; a gap of 10 min or more is a break (the run restarts); it is 0 when the last exam ended more than 10 min ago |
| `sleepiness` | 0.30 | `0.6 · circadian(t) + 0.4 · clamp(hours on duty / 24)` |
| `rushing` | 0.10 | `clamp((median_span − median_hour) / (0.5 · median_span))`: the exams that ended in the last hour are much shorter than the span's median (people speed up under load). 0 with fewer than 3 exams in the hour |

`no_break` is weighted up on purpose (2026-11-12): unbroken work also stands in, a little, for accumulated strain, which the index otherwise does not model (a leaky accumulator was considered and left for later).

`index = round(100 · Σ weight · component)`; the five components are also sent (0–100) as `strain_c` with every point.

### Sleepiness

Inspired by the two-process model of sleep regulation (a homeostatic pressure that rises with time awake, plus a circadian rhythm), reduced to what can be known here:

- **circadian(t)**: an *assumed* curve, linearly interpolated between these (hour, value) nodes: `0:00 .65 · 2:00 .85 · 4:00 1.0 · 6:00 .85 · 8:00 .40 · 10:00 .15 · 12:00 .20 · 14:00 .40 · 15:00 .40 · 16:00 .25 · 18:00 .10 · 20:00 .20 · 22:00 .45 · 24:00 .65`. Deepest between 02:00 and 06:00, a smaller dip after lunch, best mid-morning and early evening.
- **duty hours**: hours since the duty block began, as a stand-in for time awake. Blocks (`duty_start()`): weekdays, day shift from 08:00 and on-call from 14:00 to 08:00; Saturdays and Sundays from 08:00 to 08:00; before 08:00 a point belongs to the previous day's block. **Holidays are not known** and are treated as ordinary days.

The duty clock is only a proxy: someone awake long before the shift, or resting during a quiet night, differs from it.

## Worked example

Yesterday 01:00: ρ 0.57, L 2.46, W 42 min, 4 h or more of unbroken work, 11 h on duty (since 14:00), circadian 0.75.
`load` 39 · `pressure` 94 · `no_break` 100 · `sleepiness` 63 · `rushing` 0
→ 0.20·39 + 0.15·94 + 0.25·100 + 0.30·63 + 0.10·0 = 65.8 → **66**.

## How to read the numbers

- Rough bands used for the readout colour: below 40 muted, 40–64 orange, 65 and over red. They are display thresholds, not risk classes.
- It is meaningful for comparing times and days of *this* queue. It is not comparable with another department or another tool.
- Coverage limits apply: `no_break`, `rushing` and the measured ρ need PACS exam starts (see coverage in the hero subtitle); where there are none they fall back or read 0.
- Seen live (2026-11-12): `pressure` saturates often because waits of 30–60 min are normal for this queue, so it discriminates little. `QUEUE_REF` / `WAIT_REF_MIN` should be revisited after a few days of watching.

## Changing it

All tunables are module constants in `strain.py`: `WEIGHTS` (must sum to 1, tested), `LOAD_FLOOR`, `QUEUE_REF`, `WAIT_REF_MIN`, `BREAK_GAP`, `NO_BREAK_REF`, `DUTY_REF_H`, `RUSH_*`, `CIRCADIAN`. Tests: `python3 runtests.py strain`.

## Validating it (not done)

A calibration needs outcomes, which do not exist here. A defensible next step would be a *retrospective check of the proxies* (do exam duration, report length or the share of "normal" template reports vary with the hour and the load?), and, much slower, a link to follow-up findings (a CT or surgery within 72 h that contradicts the ultrasound). Neither is built.

## References to check before relying on them

Quoted from memory, not verified here: Borbély, *a two process model of sleep regulation* (1982); Folkard & Tucker, *Shift work, safety and productivity* (2003: roughly 1.3× the day risk at night, rising over consecutive nights and with long shifts); the radiology literature on workload, fatigue and interpretive error (e.g. studies of error rate against shift length and volume).
