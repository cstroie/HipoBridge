# Strain index (UPU ultrasound)

`strain.py`, computed per 10-minute point by `queuestats.compute()` and shown on the Schedule tab: the queue graph's dotted line, the hover readout (`strain NN`, tooltip = its parts) and the hero's Strain tile. Added 2026-11-12; rebuilt the same day from the owner's experience of on-call nights.

## What it is, and is not

A **relative 0–100 index of how adverse the working conditions of the UPU ultrasound radiologist are at a moment**. It lets two moments, hours or days be compared.

It is **not**:
- a probability of missing a pathology, of a superficial read, or of anyone losing their temper. There are no outcomes (misses, addenda, discrepancies, complaints) to calibrate against, and nothing in the data measures temper;
- calibrated: every weight and reference below is an **assumption**, chosen to be plausible, matched to the owner's account of on-call nights, and kept in one place (the constants at the top of `strain.py`);
- a measure of a person. It describes the *system* (load, queue, work done, clock). Do not break it down per radiologist or use it to assess individuals.

Read it as "conditions known to raise the risk of errors, hurried reads and short tempers", nothing more.

## The facts it rests on (owner, 2026-11-12)

- One ultrasound runs from calling the patient (1–2 min), preparation, the scan, talking to the patient and discharge to the **written report**. Nothing else starts before the report (rare exceptions). So an exam's busy time is *PACS study start → report validation*.
- The radiologist who does the UPU ultrasounds also does the **ward ultrasounds**.
- The on-call radiologist **also works the morning**: the duty block is 08:00 → 08:00.
- The strain at 03:00–05:00 after 40–50 ultrasounds is **very high even with a short queue**: it builds up over the duty, and an idle gap of 10 minutes is not rest.
- "Short exams with long spaces between them while a queue waits" is a sign of fatigue: getting rid of the patients fast.
- X-rays and CT are not counted. There are usually two radiologists, which the owner considers compensates.
- A **burst of arrivals** adds pressure over the next 1–2 hours.

## Formula

Two parts, each 0..1:

```
index   = 100 · (1 − (1 − now) · (1 − fatigue))
now     = 0.35 · load + 0.25 · pressure + 0.20 · burst + 0.20 · rushing
fatigue = accumulated · (0.5 + 0.5 · sleepiness)
```

Either part alone raises the index; both together raise it more. With nothing done since 08:00 and nobody waiting it reads 0 at any hour. It stays high while the room is idle late in a long block: it describes the conditions the next patient meets, not the work of that minute.

## The parts

`clamp(v) = min(1, max(0, v))`. All parts are sent 0–100 as `strain_c` with every point, `now` and `fatigue` included.

### now: the moment's work

| Part | Weight | Definition |
|---|---|---|
| `load` | 0.35 | `clamp((ρ − 0.30) / 0.70)`, ρ the room's utilisation of the hour: (UPU requests + ward studies started) × mean exam length (`rho_room`). 0 at 30 %, 1 at 100 % or more |
| `pressure` | 0.25 | the worst of: people waiting `L / L_ref`, mean wait `W / W_ref`, the **longest wait** at that moment `/ (2 · W_ref)` (clinicians call about the patient waiting longest, not about the average). `L_ref`, `W_ref` = the span's 90th percentile of the hourly L and W, never under 3 people / 45 min (`strain_refs` in the response) |
| `burst` | 0.20 | the worst recent burst of requests: for every 30-minute window ending at a request in the last 2 hours, the requests in it beyond what the room clears in half an hour (capacity × 0.5 h, capacity = 1 / mean exam length, 4/h when unknown), over 3. Felt fully for 1 hour after the window, fading linearly to 0 at 2 hours. Steady arrivals at the same ρ read 0 |
| `rushing` | 0.20 | `shorter × clamp(idle_waiting / 0.25)`: both needed. Fast exams back to back are efficiency; idle gaps alone may be a CT being read |

- **`shorter`**: each exam's length over the median length of exams **of the same regions** (`abdomen+pelvis`, `hip`…, from the report page's studies, at least 3 of a kind, else all exams). The median of the hour's ratios: 1 = usual, 0.5 = half as long. `clamp((1 − median) / 0.5)`; 0 with fewer than 3 exams in the hour.
- **`idle_waiting`**: the share of the hour with someone waiting and the room idle, the first 5 minutes of each idle gap left out (calling and preparing the next patient).

### fatigue: what the duty has cost

- **`accumulated`**: the work done since the duty began (08:00), as an integral:
  - busy time adds up: UPU exams (PACS start → report), ward studies and UPU exams with no measured end (the median exam length, cut at the next start);
  - an idle gap **under 30 minutes is not rest**: it changes nothing;
  - a gap of 30 minutes or more is rest: for its whole length the accumulated work decays with a **half-life of 8 hours** (a 2.5-hour rest takes off about 20 %);
  - read on a saturating scale, `1 − 2^(−hours / 4)`: 4 busy hours (about 20 exams) = 50 %, 8 h = 75 %, 12 h = 88 %. It nears 1 and never clips, so a heavy night still differs from a very heavy one.
- **`sleepiness`** = `0.6 · circadian(t) + 0.4 · clamp(hours since 08:00 / 24)`:
  - **circadian(t)**: an *assumed* curve inspired by the two-process model's process C, linear between `0:00 .65 · 2:00 .85 · 4:00 1.0 · 6:00 .85 · 8:00 .40 · 10:00 .15 · 12:00 .20 · 14:00 .40 · 15:00 .40 · 16:00 .25 · 18:00 .10 · 20:00 .20 · 22:00 .45 · 24:00 .65`. Deepest 02:00–06:00, a smaller dip after lunch;
  - **hours on duty**: since 08:00 (before 08:00, since the day before's). Holidays are not known.
- The `0.5 +` floor: fully rested, the accumulated work counts half; at the deepest of the night after a long block, fully.

## What it gives

Computed with `strain.score()`; 12-minute exams spread evenly since the duty began, requests arriving steadily at 4 an hour unless a burst is named (6 requests in 15 minutes), capacity 5 exams an hour.

| Moment | Index | now | burst | accumulated | sleepiness | fatigue |
|---|---|---|---|---|---|---|
| 10:00, 8 done since 08:00, 1 waiting | **29** | 18 | 0 | 24 | 12 | 14 |
| 12:00, 15 done, 5 waiting | **66** | 55 | 0 | 41 | 19 | 24 |
| 14:00, 20 done, 2 waiting | **55** | 32 | 0 | 50 | 34 | 34 |
| 20:00, 30 done, 2 waiting | **61** | 32 | 0 | 65 | 32 | 43 |
| 21:00, 30 done, 6 arrived 20:30-20:45, 4 waiting | **86** | 75 | 100 | 65 | 41 | 46 |
| 22:00, the same burst an hour on, 2 waiting | **75** | 47 | 75 | 69 | 50 | 52 |
| 00:00, 38 done, 2 waiting | **73** | 32 | 0 | 73 | 66 | 61 |
| 04:00, 25 done (quiet night), 2 waiting | **53** | 27 | 0 | 38 | 93 | 36 |
| 04:00, 45 done, nobody waiting | **76** | 0 | 0 | 79 | 93 | 76 |
| 04:00, 45 done, 2 waiting | **83** | 27 | 0 | 79 | 93 | 76 |
| 04:00, 45 done, 5 waiting | **88** | 50 | 0 | 79 | 93 | 76 |
| 04:00, 45 done, a burst at 03:00, 3 waiting | **93** | 70 | 100 | 79 | 93 | 76 |
| 04:00, 45 done, rested 01:00-03:30, 2 waiting | **76** | 27 | 0 | 69 | 93 | 67 |
| 04:00, 45 done, short exams + idle while 5 wait | **93** | 70 | 0 | 79 | 93 | 76 |
| 07:30, 55 done, 3 waiting | **83** | 40 | 0 | 85 | 70 | 72 |

The quiet night reads lower than its 25 exams suggest: spread over 20 hours they leave gaps over 30 minutes, which count as rest.

## How to read the numbers

- Readout colours: below 40 muted, 40–64 orange, 65 and over red. Display thresholds, not risk classes.
- Meaningful for comparing times and days of *this* queue; not comparable with another department or tool.
- `pressure` is judged against the span shown, so the same moment reads differently in the 12 h, 24 h and multi-day views. The other parts do not depend on the span.
- Coverage limits: `accumulated`, `rushing` and the measured ρ need PACS exam starts (coverage in the hero subtitle); `shorter` by region needs the report pages cached (else all exams are one kind). Without the PACS day list there are no ward studies, and the load is understated.
- A ward study's length is not measured (its report time is not read): the median exam length, cut at the next start.
- X-rays and CT are not counted (two radiologists, see above). A gap spent reading a CT can still show as `idle_waiting`; `rushing` needs short exams as well, which limits that.

## History

1. **First version** (`cf85653`): a weighted sum, with sleepiness a 0.30 term: an empty room read about 25 at 04:00, mostly a clock curve.
2. **Fatigue as a multiplier** (`c0f002c`): `work × (0.5 + 0.5 · sleepiness)`, with `no_break` (back-to-back minutes, reset by any 10-minute gap). The owner's 04:00 case (45 done, 5 waiting) read 54, and 38 after a 15-minute pause: nothing remembered the night's work.
3. **A decaying integral since 14:00** (`10bdba8`): fixed the memory, but decayed during work too, and the block started at 14:00.
4. **Rest-only decay** (`2ca90d7`): the duty block starts at 08:00; only a rest of 30 minutes or more decays the work; a saturating scale; `shorter` by exam regions; the longest wait in `pressure`; calling time left out of `idle_waiting`; ward studies counted at every hour.
5. **Now**: bursts of arrivals, felt over the next 1–2 hours (`burst`).

## Changing it

All tunables are constants at the top of `strain.py`:

| Constant | Value | Meaning |
|---|---|---|
| `NOW_WEIGHTS` | 0.35 / 0.25 / 0.20 / 0.20 | load / pressure / burst / rushing (sum to 1, tested) |
| `LOAD_FLOOR` | 0.30 | utilisation that counts as no load |
| `QUEUE_REF`, `WAIT_REF_MIN` | 3, 45 min | the floors of the span references |
| `OLDEST_FACTOR` | 2 | the longest wait is full at twice the wait reference |
| `SHORT_REF`, `SHORT_MIN_SAMPLES` | 0.5, 3 | half the usual length = 1; exams needed in the hour |
| `BURST_SPAN`, `BURST_REF` | 30 min, 3 | arrivals counted together; patients beyond capacity = 1 |
| `BURST_HOLD`, `BURST_FADE` | 1 h, 2 h | felt fully, then gone |
| `CAPACITY_DEFAULT_H` | 4 | exams per hour when the mean length is unknown |
| `IDLE_REF`, `CALL_ALLOWANCE` | 0.25, 5 min | a quarter of the hour idle while people wait = 1; calling is not idle |
| `REST_MIN` | 30 min | a shorter idle gap is not rest |
| `ACCUM_HALF_LIFE_H` | 8 h | decay of the accumulated work during rest |
| `ACCUM_HALF_FULL_H` | 4 h | busy hours that make `accumulated` half full |
| `FATIGUE_FLOOR` | 0.5 | share of the accumulated work counted fully rested |
| `DUTY_START_HOUR`, `DUTY_REF_H` | 08:00, 24 h | the duty block |
| `CIRCADIAN` | see above | the assumed curve |

`queuestats.REGION_MIN_SAMPLES` (3) sets how many exams of a kind give that kind its own median. Tests: `python3 runtests.py strain` and `python3 runtests.py queuestats`. The table above is reproduced by scoring `strain.Moment`s by hand.

## Validating it (not done)

A calibration needs outcomes, which do not exist here. Defensible next steps:
- a *retrospective check of the proxies*: do report length or the share of "normal" template reports vary with the index, the hour and the accumulated work?
- **a sensitivity test**: score a month with many random weight sets; if the hours and days keep their ranking, the exact weights matter little;
- much slower, a link to follow-up findings (a CT or surgery within 72 h that contradicts the ultrasound).

Not modelled yet: night wake-ups (work resuming after a long quiet, broken sleep), triage colour, consecutive duties (needs the radiology roster: a count, never a name).

## References to check before relying on them

Quoted from memory, not verified here: Borbély, *a two process model of sleep regulation* (1982); Folkard & Tucker, *Shift work, safety and productivity* (2003: roughly 1.3× the day risk at night, rising over consecutive nights and with long shifts); the radiology literature on workload, fatigue and interpretive error (e.g. studies of error rate against shift length and volume).
