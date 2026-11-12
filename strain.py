"""Relative strain index of the UPU ultrasound radiologist, per time point.

NOT a probability and NOT calibrated: there are no outcomes (misses,
addenda, complaints) to calibrate against, and nothing measures temper.
It is a 0-100 index of how adverse the working conditions are at a moment,
built from signals the queue data already has, so that two moments (or two
days) can be compared. The weights are assumptions, kept in one place
(WEIGHTS) and shown with every point (`strain_c`), so each can be argued
with. Read it as "conditions known to raise the risk of errors, hurried
reads and short tempers", never as "an error is X% likely".

Two parts, each 0..1 (2026-11-12, owner's experience: at 03:00-05:00
after 40-50 ultrasounds the strain is very high even with a short queue):

  now      the moment's work, weighted (WEIGHTS):
    load       rho of the hour (lam / mu, the ward studies included): 0 at
               30 %, 1 at 100 % and over
    pressure   people waiting: the queue length or the mean wait, whichever
               is worse, against references the caller gives (queuestats:
               the span's 90th percentile, never under 3 waiting / 45 min)
    rushing    "get rid of them fast" (owner): the last hour's exams much
               shorter than the span's median (50 % shorter = 1, needs 3)
               AND the room idle while people wait (a quarter of the hour =
               1); the product, so neither alone counts
  fatigue  accumulated * (FATIGUE_FLOOR + (1 - FATIGUE_FLOOR) * sleepiness)
    accumulated  the integral of the work done since the duty block began
               (UPU exams and ward studies, busy time), each minute fading
               with a half-life of ACCUM_HALF_LIFE (rest recovers slowly on
               duty): ACCUM_REF of it = 1. A break does not reset it.
    sleepiness 0.6 * circadian + 0.4 * time on duty
               circadian  assumed shape of the two-process model's process C:
                          deepest 02:00-06:00, a smaller dip after lunch
               duty       hours since the duty block began (weekdays: day
                          08:00, on-call 14:00 -> 08:00; weekends 08:00 ->
                          08:00; holidays not known), 24 h = 1

  index = 100 * (1 - (1 - now) * (1 - fatigue))

Either part alone can raise the index, both together raise it more: a short
queue at 04:00 after a long night reads high, a long queue at 10:00 rested
too. With nothing done since the block began and nobody waiting it is 0.
"""
import math
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

# The moment's work components (sum to 1)
WEIGHTS = {'load': 0.45, 'pressure': 0.30, 'rushing': 0.25}
FATIGUE_FLOOR = 0.5                   # the share of the accumulated work counted fully rested
ACCUM_HALF_LIFE_H = 8.0               # a minute of work 8 h ago counts half
ACCUM_REF_H = 6.0                     # decayed busy hours that count as full (about 45 exams
                                      # of 12 min spread over 14 h, owner's 04:00 example)
IDLE_REF = 0.25                       # share of the hour idle while people wait

LOAD_FLOOR = 0.30
QUEUE_REF = 3.0                       # people waiting: the default, and queuestats' floor
WAIT_REF_MIN = 45.0                   # minutes: likewise
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


def accumulated_hours(busy: List[Tuple[datetime, datetime]], t: datetime,
                      since: Optional[datetime] = None) -> float:
    """The integral of the busy time in [since, t] (the duty block's start by
    default), each moment u weighted 2 ** -((t - u) / half-life): exactly,
    per interval, H / ln 2 * (2 ** -((t - e) / H) - 2 ** -((t - s) / H))."""
    since = since or duty_start(t)
    h = ACCUM_HALF_LIFE_H
    total = 0.0
    for s, e in busy:
        s, e = max(s, since), min(e, t)
        if e <= s:
            continue
        age_e = (t - e).total_seconds() / 3600.0
        age_s = (t - s).total_seconds() / 3600.0
        total += h / math.log(2) * (2 ** (-age_e / h) - 2 ** (-age_s / h))
    return total


def shorter(window_minutes: List[float], span_median: Optional[float]) -> float:
    """How much shorter the hour's exams are than the span's median: 50 % = 1."""
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
           queue_ref: float = QUEUE_REF, wait_ref: float = WAIT_REF_MIN,
           idle_waiting: float = 0.0) -> dict:
    """{'index': 0-100, 'c': {component: 0-100}} at moment t.

    `samples` are the measured UPU exams (rushing), `busy` all the work done
    (accumulated; the samples when not given), `idle_waiting` the share of
    the hour with someone waiting and the room idle."""
    window_minutes = [(e - s).total_seconds() / 60.0 for s, e in samples if t - window < e <= t]
    c = {
        'load': clamp(((rho or 0.0) - LOAD_FLOOR) / (1.0 - LOAD_FLOOR)),
        'pressure': max(clamp((queue or 0.0) / queue_ref), clamp((wait_min or 0.0) / wait_ref)),
        'rushing': shorter(window_minutes, span_median) * clamp((idle_waiting or 0.0) / IDLE_REF),
    }
    now = sum(WEIGHTS[k] * v for k, v in c.items())
    c['accumulated'] = clamp(accumulated_hours(busy if busy is not None else samples, t) / ACCUM_REF_H)
    c['sleepiness'] = sleepiness(t)
    fatigue = c['accumulated'] * (FATIGUE_FLOOR + (1.0 - FATIGUE_FLOOR) * c['sleepiness'])
    c['now'], c['fatigue'] = now, fatigue
    index = 100.0 * (1.0 - (1.0 - now) * (1.0 - fatigue))
    return {'index': int(round(index)), 'c': {k: int(round(100 * v)) for k, v in c.items()}}
