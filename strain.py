"""Relative strain index of the UPU ultrasound radiologist, per time point.

NOT a probability and NOT calibrated: there are no outcomes (misses,
addenda, complaints) to calibrate against, and nothing measures temper.
It is a 0-100 index of how adverse the working conditions are at a moment,
built from signals the queue data already has, so that two moments (or two
days) can be compared. The weights and references are assumptions, kept in
one place below and shown with every point (`strain_c`), so each can be
argued with. Read it as "conditions known to raise the risk of errors,
hurried reads and short tempers", never as "an error is X% likely".
Full method: docs/STRAIN_INDEX.md.

Two parts, each 0..1, combined so that either alone raises the index and
both together raise it more:

    index = 100 * (1 - (1 - now) * (1 - fatigue))

now: the moment's work (NOW_WEIGHTS)
    load      the room's utilisation of the hour (UPU and ward studies)
    pressure  people waiting: count, mean wait or the longest wait
    burst     a burst of arrivals beyond what the room clears in half an
              hour, felt fully for an hour after it and fading by two
              (owner: bursts add pressure over the next 1-2 hours)
    rushing   "get rid of them fast" (owner): exams much shorter than usual
              for their region AND the room idle while people wait

fatigue = accumulated * (FATIGUE_FLOOR + (1 - FATIGUE_FLOOR) * sleepiness)
    accumulated  the busy time since the duty began, an integral that only
                 a real rest (an idle gap of REST_MIN or more) lets decay,
                 with a half-life of ACCUM_HALF_LIFE_H; read on a saturating
                 scale, 1 - 2 ** -(hours / ACCUM_HALF_FULL_H)
    sleepiness   an assumed circadian curve and the hours on duty

The duty block runs 08:00 -> 08:00 every day: the on-call radiologist also
works the morning (owner, 2026-11-12). Holidays are not known.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

Interval = Tuple[datetime, datetime]

# --- now ------------------------------------------------------------------
NOW_WEIGHTS = {'load': 0.35, 'pressure': 0.25, 'burst': 0.20, 'rushing': 0.20}   # sum to 1
LOAD_FLOOR = 0.30                 # utilisation that counts as no load
QUEUE_REF = 3.0                   # people waiting = full pressure (a floor: queuestats
WAIT_REF_MIN = 45.0               # mean wait, minutes      raises both to the span's p90)
OLDEST_FACTOR = 2.0               # the longest wait is full at twice the wait reference
SHORT_REF = 0.5                   # exams 50 % shorter than their region's median = 1
SHORT_MIN_SAMPLES = 3             # exams needed in the hour to judge
IDLE_REF = 0.25                   # a quarter of the hour idle while people wait = 1
CALL_ALLOWANCE = timedelta(minutes=5)   # calling and preparing the next patient is not idle
BURST_SPAN = timedelta(minutes=30)      # arrivals counted together
BURST_REF = 3.0                         # patients beyond what the room clears in BURST_SPAN = 1
BURST_HOLD = timedelta(hours=1)         # felt fully this long after the burst,
BURST_FADE = timedelta(hours=2)         # then fading linearly to nothing at this age
CAPACITY_DEFAULT_H = 4.0                # exams per hour when no capacity is known

# --- fatigue --------------------------------------------------------------
FATIGUE_FLOOR = 0.5               # the share of the accumulated work counted fully rested
ACCUM_HALF_FULL_H = 2.5           # busy hours that make it half full (about 17 exams of 9 min);
                                  # 5 h = 75 %, 7.5 h = 88 %: it nears 1, never clips. Real exams
                                  # last 7-9 min (2026-11-12): the owner's 40-50 exams ~ 80 %
ACCUM_HALF_LIFE_H = 8.0           # during rest, the accumulated work halves in 8 h
REST_MIN = timedelta(minutes=30)  # a shorter idle gap is not rest (owner, 2026-11-12)
DUTY_START_HOUR = 8
DUTY_REF_H = 24.0

# (hour, sleepiness 0..1): assumed shape, not measured
CIRCADIAN = [(0, 0.65), (2, 0.85), (4, 1.0), (6, 0.85), (8, 0.40), (10, 0.15), (12, 0.20),
             (14, 0.40), (15, 0.40), (16, 0.25), (18, 0.10), (20, 0.20), (22, 0.45), (24, 0.65)]


@dataclass
class Moment:
    """What the queue analysis knows at one point (queuestats.compute())."""
    t: datetime
    rho: Optional[float] = None          # the room's utilisation of the hour
    queue: float = 0.0                   # L: mean number waiting over the hour
    wait: Optional[float] = None         # W: mean wait (minutes) of the hour's exams
    oldest: Optional[float] = None       # minutes the longest-waiting patient has waited at t
    idle_waiting: float = 0.0            # share of the hour idle while someone waits
    relative: List[float] = field(default_factory=list)   # the hour's exam lengths / their region's median
    arrivals: List[datetime] = field(default_factory=list)  # request times (sorted), the last BURST_FADE at least
    capacity: Optional[float] = None     # exams the room does per hour (1 / mean exam length)
    busy: List[Interval] = field(default_factory=list)    # all the work done (accumulated)


@dataclass
class Refs:
    queue: float = QUEUE_REF
    wait: float = WAIT_REF_MIN


def clamp(v: float) -> float:
    return 0.0 if v < 0 else 1.0 if v > 1 else v


# --- the clock ----------------------------------------------------------------

def circadian(t: datetime) -> float:
    h = t.hour + t.minute / 60.0
    for (h0, v0), (h1, v1) in zip(CIRCADIAN, CIRCADIAN[1:]):
        if h0 <= h <= h1:
            return v0 + (v1 - v0) * (h - h0) / (h1 - h0)
    return CIRCADIAN[-1][1]


def duty_start(t: datetime) -> datetime:
    """Start of the 08:00 -> 08:00 duty block t falls in."""
    start = t.replace(hour=DUTY_START_HOUR, minute=0, second=0, microsecond=0)
    return start if t >= start else start - timedelta(days=1)


def duty_hours(t: datetime) -> float:
    return (t - duty_start(t)).total_seconds() / 3600.0


def sleepiness(t: datetime) -> float:
    return 0.6 * circadian(t) + 0.4 * clamp(duty_hours(t) / DUTY_REF_H)


# --- the parts ----------------------------------------------------------------

def merge(intervals: List[Interval]) -> List[Interval]:
    """The union of the intervals, as sorted disjoint ones."""
    out: List[Interval] = []
    for s, e in sorted(intervals):
        if e <= s:
            continue
        if out and s <= out[-1][1]:
            if e > out[-1][1]:
                out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return out


def accumulated_hours(busy: List[Interval], t: datetime, since: Optional[datetime] = None) -> float:
    """The work accumulated at t since the duty began, in busy hours.

    Busy time adds up; an idle gap shorter than REST_MIN is part of the
    work (calling, waiting for a patient, a phone call) and changes
    nothing; a gap of REST_MIN or more is rest, and for its whole length
    the accumulated work decays with a half-life of ACCUM_HALF_LIFE_H."""
    since = since or duty_start(t)
    acc, cursor = 0.0, since
    for s, e in merge([(max(s, since), min(e, t)) for s, e in busy if e > since and s < t]):
        acc = _rest(acc, s - cursor)
        acc += (e - s).total_seconds() / 3600.0
        cursor = e
    return _rest(acc, t - cursor)


def _rest(acc: float, gap: timedelta) -> float:
    if acc <= 0 or gap < REST_MIN:
        return acc
    return acc * 2 ** (-(gap.total_seconds() / 3600.0) / ACCUM_HALF_LIFE_H)


def shorter(relative: List[float]) -> float:
    """How much shorter the hour's exams are than usual for their region
    (each exam's length over its region's median): 50 % shorter = 1."""
    if len(relative) < SHORT_MIN_SAMPLES:
        return 0.0
    vals = sorted(relative)
    mid = len(vals) // 2
    med = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2.0
    return clamp((1.0 - med) / SHORT_REF)


def burst(arrivals: List[datetime], t: datetime, capacity: Optional[float]) -> float:
    """The worst recent burst: for every BURST_SPAN window ending at an
    arrival in the last BURST_FADE, the patients beyond what the room clears
    in it (capacity * BURST_SPAN), over BURST_REF; weighted 1 up to
    BURST_HOLD after the window, fading linearly to 0 at BURST_FADE."""
    cap = (capacity or CAPACITY_DEFAULT_H) * BURST_SPAN.total_seconds() / 3600.0
    recent = [a for a in arrivals if t - BURST_FADE - BURST_SPAN < a <= t]
    worst = 0.0
    for end in recent:
        age = t - end
        if age >= BURST_FADE:
            continue
        n = sum(1 for a in recent if end - BURST_SPAN < a <= end)
        size = clamp((n - cap) / BURST_REF)
        if size <= 0:
            continue
        weight = 1.0 if age <= BURST_HOLD else (BURST_FADE - age) / (BURST_FADE - BURST_HOLD)
        worst = max(worst, size * weight)
    return worst


def score(m: Moment, refs: Optional[Refs] = None) -> dict:
    """{'index': 0-100, 'c': {part: 0-100}} at m.t."""
    refs = refs or Refs()
    oldest_ref = OLDEST_FACTOR * refs.wait
    c: Dict[str, float] = {
        'load': clamp(((m.rho or 0.0) - LOAD_FLOOR) / (1.0 - LOAD_FLOOR)),
        'pressure': max(clamp((m.queue or 0.0) / refs.queue), clamp((m.wait or 0.0) / refs.wait),
                        clamp((m.oldest or 0.0) / oldest_ref)),
        'burst': burst(m.arrivals, m.t, m.capacity),
        'rushing': shorter(m.relative) * clamp((m.idle_waiting or 0.0) / IDLE_REF),
    }
    now = sum(NOW_WEIGHTS[k] * c[k] for k in NOW_WEIGHTS)
    c['accumulated'] = 1.0 - 2 ** (-accumulated_hours(m.busy, m.t) / ACCUM_HALF_FULL_H)
    c['sleepiness'] = sleepiness(m.t)
    fatigue = c['accumulated'] * (FATIGUE_FLOOR + (1.0 - FATIGUE_FLOOR) * c['sleepiness'])
    c['now'], c['fatigue'] = now, fatigue
    index = 100.0 * (1.0 - (1.0 - now) * (1.0 - fatigue))
    return {'index': int(round(index)), 'c': {k: int(round(100 * v)) for k, v in c.items()}}
