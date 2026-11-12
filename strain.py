"""Relative strain index of the UPU ultrasound radiologist, per time point.

NOT a probability and NOT calibrated: there are no outcomes (misses,
addenda, complaints) to calibrate against, and nothing measures temper.
It is a 0-100 index of how adverse the working conditions are at a moment,
built from signals the queue data already has, so that two moments (or two
days) can be compared. The weights are assumptions, kept in one place
(WEIGHTS) and shown with every point (`strain_c`), so each can be argued
with. Read it as "conditions known to raise the risk of errors, hurried
reads and short tempers", never as "an error is X% likely".

Work components, each 0..1, weighted (WEIGHTS):
  load       rho of the hour (lam / mu, the ward studies included): 0 at
             30 %, 1 at 100 % and over
  pressure   people waiting: the queue length or the mean wait, whichever is
             worse, against references the caller gives (queuestats: the
             span's 90th percentile, never under 3 waiting / 45 min)
  no_break   minutes of back-to-back work (UPU exams and ward studies, gaps
             under 10 min): 4 h = 1
  sleepiness parts:
               circadian  assumed shape of the two-process model's process C:
                          deepest 02:00-06:00, a smaller dip after lunch
               duty       hours since the duty block began (weekdays: day
                          08:00, on-call 14:00 -> 08:00; weekends 08:00 ->
                          08:00; holidays not known), 24 h = 1
  rushing    exams of the last hour much shorter than the span's median
             (50 % shorter = 1); people speed up under load. Needs 3 exams.

Fatigue does not add to the index, it scales it (2026-11-12):

  index = 100 * work * (FATIGUE_FLOOR + (1 - FATIGUE_FLOOR) * sleepiness)

  sleepiness 0.6 * circadian + 0.4 * time on duty (below), shown as a component
             but carrying no weight of its own: with no work (no exams, nobody
             waiting) the index is 0 at any hour, and the same work weighs up to
             twice as much at 04:00 after a long block as at 10:00 rested.
"""
import math
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

# The work components (sum to 1). no_break is weighted up on purpose:
# unbroken work also stands in for accumulated strain.
WEIGHTS = {'load': 0.30, 'pressure': 0.20, 'no_break': 0.35, 'rushing': 0.15}
FATIGUE_FLOOR = 0.5                   # the share of the work counted fully rested

LOAD_FLOOR = 0.30
QUEUE_REF = 3.0                       # people waiting: the default, and queuestats' floor
WAIT_REF_MIN = 45.0                   # minutes: likewise
BREAK_GAP = timedelta(minutes=10)     # an idle gap this long is a break
NO_BREAK_REF = timedelta(hours=4)
DUTY_REF_H = 24.0
RUSH_MIN_SAMPLES = 3
RUSH_REF = 0.5

# (hour, sleepiness 0..1): assumed shape, not measured
CIRCADIAN = [(0, 0.65), (2, 0.85), (4, 1.0), (6, 0.85), (8, 0.40), (10, 0.15), (12, 0.20),
             (14, 0.40), (15, 0.40), (16, 0.25), (18, 0.10), (20, 0.20), (22, 0.45), (24, 0.65)]


def clamp(v: float) -> float:
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def circadian(t: datetime) -> float:
    h = t.hour + t.minute / 60.0
    for (h0, v0), (h1, v1) in zip(CIRCADIAN, CIRCADIAN[1:]):
        if h0 <= h <= h1:
            return v0 + (v1 - v0) * (h - h0) / (h1 - h0)
    return CIRCADIAN[-1][1]


def duty_start(t: datetime) -> datetime:
    """Start of the duty block t falls in (holidays are not known)."""
    day = t.replace(hour=0, minute=0, second=0, microsecond=0)
    if t.hour < 8:                      # still the block of the day before
        prev = day - timedelta(days=1)
        return prev.replace(hour=14 if prev.weekday() < 5 else 8)
    if day.weekday() >= 5:
        return day.replace(hour=8)
    return day.replace(hour=14 if t.hour >= 14 else 8)


def duty_hours(t: datetime) -> float:
    return (t - duty_start(t)).total_seconds() / 3600.0


def run_without_break(samples: List[Tuple[datetime, datetime]], t: datetime) -> timedelta:
    """Length of the back-to-back work ending at t: exams (start, end) chained
    with gaps under BREAK_GAP, the last one ending (or still running) within
    BREAK_GAP of t. Zero after a break."""
    done = sorted((s, e) for s, e in samples if s <= t)
    if not done:
        return timedelta(0)
    chain_start = chain_end = None
    for s, e in done:
        e = min(e, t)
        if chain_end is None or s - chain_end > BREAK_GAP:
            chain_start = s
        chain_end = e if chain_end is None else max(chain_end, e)
    if t - chain_end > BREAK_GAP:
        return timedelta(0)
    return chain_end - chain_start


def rushing(window_minutes: List[float], span_median: Optional[float]) -> float:
    if len(window_minutes) < RUSH_MIN_SAMPLES or not span_median:
        return 0.0
    vals = sorted(window_minutes)
    mid = len(vals) // 2
    med = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2.0
    return clamp((span_median - med) / (RUSH_REF * span_median))


def sleepiness(t: datetime) -> float:
    return 0.6 * circadian(t) + 0.4 * clamp(duty_hours(t) / DUTY_REF_H)


def strain(t: datetime, rho: Optional[float], queue: float, wait_min: Optional[float],
           samples: List[Tuple[datetime, datetime]], span_median: Optional[float],
           window: timedelta = timedelta(hours=1), busy: Optional[List[Tuple[datetime, datetime]]] = None,
           queue_ref: float = QUEUE_REF, wait_ref: float = WAIT_REF_MIN) -> dict:
    """{'index': 0-100, 'c': {component: 0-100}} at moment t.

    `samples` are the measured UPU exams (rushing), `busy` all the room's
    work (no_break; the samples when not given)."""
    window_minutes = [(e - s).total_seconds() / 60.0 for s, e in samples if t - window < e <= t]
    c = {
        'load': clamp(((rho or 0.0) - LOAD_FLOOR) / (1.0 - LOAD_FLOOR)),
        'pressure': max(clamp((queue or 0.0) / queue_ref), clamp((wait_min or 0.0) / wait_ref)),
        'no_break': clamp(run_without_break(busy if busy is not None else samples, t) / NO_BREAK_REF),
        'rushing': rushing(window_minutes, span_median),
    }
    work = sum(WEIGHTS[k] * v for k, v in c.items())
    c['sleepiness'] = sleepiness(t)
    index = 100.0 * work * (FATIGUE_FLOOR + (1.0 - FATIGUE_FLOOR) * c['sleepiness'])
    return {'index': int(round(index)), 'c': {k: int(round(100 * v)) for k, v in c.items()}}
