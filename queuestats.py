"""Queue-theory metrics for the Schedule tab (GET /api/schedule/queue).

Pure computation: no aiohttp, no Hipocrate. The handler in hippobridge.py
fetches the schedule rows and the cache-only times (report validation, UPU
presentation) and hands them here. Nothing is stored; every call recomputes
from the timestamps, so any past moment can be analysed as well as now.

Scope (2026-11-11, owner's call): ultrasound requests from UPU only: one
server, so one queue and a meaningful rho. Other modalities and wards are
left out (in_scope()); the handler fetches only the ultrasound lab.

Each request is a job passing through two queues:

    UPU arrival -> request (t_req) -> exam done (t_exam) -> report validated (t_rep)
                  '---- exam queue -----'  '------ report queue ------'

The UPU leg (door-to-request) has no queue of its own here, only a mean
time. Per window [t - window, t]:

    lam  arrivals per hour (requests made)
    x    departures per hour (exams done: the throughput)
    L    time-average number waiting (the exact overlap of every job's
         interval with the window, divided by the window)
    W    mean wait in minutes of the jobs that departed in the window
    little  lam * W in jobs: Little's law says it should match L
    mu   service rate: the demonstrated capacity, the 90th percentile of the
         hourly departures over the span (rolling, 10-minute step). There
         are no true service times in Hipocrate (service_rate()).
    rho  utilisation lam / mu
    busy share of the window with at least one job waiting

The same set with an `r` suffix is the report queue.

Rules for unknown times (docs/ARCHITECTURE.md, 2026-11-11):
  * performed_at of exactly 00:00 is a date-only value: unknown.
  * A row whose status says it has left (completed/ended) but whose leaving
    time is unknown is dropped from that stage entirely (arrivals, L, W),
    never counted as still waiting; it shows in `coverage`. A completed row
    with no performed_at but a cached report time uses the report time as
    its exam time (the two collapse).
  * The row's status, not the cache, decides whether a job has left: a
    stale cached report page without a validation date never means "not yet
    reported".
"""

from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

import strain as strain_index

SCOPE_MODALITY = 'eco'   # ultrasound
SCOPE_LAB_ID = '28'      # its Hipocrate laboratory (HippoClientSchedule._LAB_ID_TO_MODALITY)
SCOPE_SECTION = 'UPU'
EXCLUDED_STATUSES = {'on-hold', 'entered-in-error', 'revoked'}
LEFT_STATUSES = {'completed', 'ended'}
OPEN_STATUSES = {'draft', 'active'}

UPU_MAX_LEAD = timedelta(hours=24)
# A job still open longer than its modality usually takes (the 95th
# percentile of that modality's finished waits at the stage, within
# OPEN_MIN..OPEN_MAX; the pooled one when fewer than OPEN_SAMPLES finished)
# is a stale row (never performed, never cancelled, or a report nobody will
# validate), not a patient in the queue: it stops counting then, and shows
# in coverage as stale. Without it a handful of abandoned rows keep every
# queue "busy" all night and inflate L, mu and rho.
OPEN_MIN = timedelta(hours=2)
OPEN_MAX = timedelta(hours=24)
OPEN_SAMPLES = 5
FETCH_LIMIT = 2000
# PACS study start (pacs.py: StudyTime). Hipocrate records no exam start, the
# modality's MPPS is not available, and the PACS returns no per-image times
# (checked live 2026-11-12: image/series-level C-FIND repeats StudyTime
# only), so the end of an exam is unknown; it is taken from the written report
# (an ultrasound exam ends with it) or the next exam's start (service_samples()).
PACS_SLACK = timedelta(minutes=15)    # a study may start a little before the request is entered
SERVICE_MAX = timedelta(hours=2)      # a longer start-to-end is not one ultrasound exam
SERVICE_MIN_SAMPLES = 5               # samples needed before the measured rho is shown


def parse_ts(value) -> Optional[datetime]:
    """'YYYY-MM-DD HH:MM', ISO with T/seconds, or 'dd/mm/yyyy HH:MM' -> datetime."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M',
                '%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y %H:%M:%S'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def parse_performed(value) -> Optional[datetime]:
    """performed_at, with exactly 00:00 read as a date-only (unknown) time."""
    dt = parse_ts(value)
    if dt is None or (dt.hour == 0 and dt.minute == 0):
        return None
    return dt


def parse_anchor(value, now: datetime, step_min: int = 10) -> datetime:
    """The analysis moment: ?end= if given (a bare date means its 24:00),
    else now; never later than now; rounded down to the step."""
    anchor = None
    if value:
        s = str(value).strip()
        try:
            anchor = datetime.strptime(s, '%Y-%m-%d') + timedelta(days=1)
        except ValueError:
            anchor = parse_ts(s)
    if anchor is None or anchor > now:
        anchor = now
    anchor = anchor.replace(second=0, microsecond=0)
    return anchor - timedelta(minutes=anchor.minute % step_min)


def in_scope(row: dict) -> bool:
    """A UPU ultrasound request that was not cancelled or never sent."""
    return (row.get('modality') == SCOPE_MODALITY
            and (row.get('section') or '').strip().upper() == SCOPE_SECTION
            and row.get('status') not in EXCLUDED_STATUSES)


def latest_validation(studies) -> Optional[datetime]:
    """The request leaves when its last study is validated."""
    times = [parse_ts(s.get('validation_date')) for s in (studies or []) if isinstance(s, dict)]
    times = [t for t in times if t]
    return max(times) if times else None


def fupu_arrival(date_str, time_str) -> Optional[datetime]:
    """FUPU sheet date 'dd/mm/yyyy' + intake time 'HH:MM' -> datetime."""
    if not date_str or not time_str:
        return None
    return parse_ts(f"{date_str.strip()} {time_str.strip()}")


def pick_presentation(times: Iterable[datetime], t_req: datetime) -> Optional[datetime]:
    """The most recent presentation at or before the request, within 24 h."""
    best = None
    for t in times:
        if t and t <= t_req and t_req - t <= UPU_MAX_LEAD and (best is None or t > best):
            best = t
    return best


def pick_study(studies, t_req: datetime, t_perf: Optional[datetime] = None) -> Optional[datetime]:
    """Start of the PACS study that belongs to this request.

    `studies` are the same-patient, same-modality studies the PACS returned
    (dicts with an ISO 'start'). A candidate starts no earlier than
    PACS_SLACK before the request and no later than OPEN_MAX after it; with a
    performed_at the nearest one wins, else the earliest. The start is
    clamped to the request time (an exam cannot wait a negative time).
    None when none fits."""
    cands = []
    for st in studies or []:
        a = parse_ts(st.get('start'))
        if a is not None and t_req - PACS_SLACK <= a <= t_req + OPEN_MAX:
            cands.append(a)
    if not cands:
        return None
    start = min(cands, key=(lambda a: abs(a - t_perf)) if t_perf else (lambda a: a))
    return max(start, t_req)


def build_jobs(rows: List[dict], report_times: Dict[str, Optional[datetime]],
               arrivals: Dict[str, Optional[datetime]],
               pacs_studies: Optional[Dict[str, list]] = None) -> List[dict]:
    """One job per imaging row, with each stage as an interval [start, end)
    (end None = still waiting), or None when the stage is unknown/not reached.

    With a PACS study the exam stage ends when the exam *starts* (the patient
    leaves the queue for the room) and a `service` stage (start, end) exists;
    the report stage starts at the exam's end. Without one, performed_at
    stands for all of it, as before."""
    pacs_studies = pacs_studies or {}
    jobs = []
    for r in rows:
        if not in_scope(r):
            continue
        t_req = parse_ts(r.get('date_time'))
        if t_req is None:
            continue
        rid = str(r.get('request_id') or '')
        status = r.get('status')
        left = status in LEFT_STATUSES
        t_rep = report_times.get(rid)
        t_exam = parse_performed(r.get('performed_at'))
        t_perf = t_exam
        if t_exam is None and left and t_rep is not None:
            t_exam = t_rep

        # An exam time before the request is a clock/date glitch: the job is
        # dropped from both stages (not left in the report queue alone) and
        # counted in coverage as inconsistent.
        inconsistent = t_exam is not None and t_exam < t_req
        if inconsistent:
            t_exam = None

        t_start = None
        if not inconsistent:
            t_start = pick_study(pacs_studies.get(rid), t_req, t_perf)
        # the wait ends when the exam starts (PACS), else at performed_at
        t_left = t_start or t_exam
        t_out = t_exam or t_start            # the exam is over: the report stage starts

        exam = None
        if inconsistent:
            pass
        elif t_left is not None:
            exam = (t_req, t_left)
        elif not left:
            exam = (t_req, None)

        report = None
        if inconsistent:
            pass
        elif t_out is not None:
            if t_rep is not None and t_rep >= t_out:
                report = (t_out, t_rep)
            elif not left:
                report = (t_out, None)


        jobs.append({
            'id': rid,
            'modality': r.get('modality'),
            'upu': (r.get('section') or '').strip().upper() == 'UPU',
            'left': left,
            't_req': t_req,
            't_arr': arrivals.get(rid),
            'exam': exam,
            'report': report,
            'pacs_start': t_start is not None,
            't_start': t_start,
            't_rep': t_rep,
            'inconsistent': inconsistent,
            'exam_known': t_left is not None,
            'report_known': t_rep is not None,
        })
    return jobs


def _hours(td: timedelta) -> float:
    return td.total_seconds() / 3600.0


def _parts(iv):
    """(start, end, cap): an interval is (start, end) or, once open_caps()
    has run, an open one (start, None, cap)."""
    return (iv[0], iv[1], iv[2]) if len(iv) > 2 else (iv[0], iv[1], OPEN_MAX)


def _open_end(start: datetime, end: Optional[datetime], b: datetime, cap: timedelta = OPEN_MAX) -> datetime:
    """The interval's end clipped to b; an open one stops counting after cap."""
    if end is None:
        end = start + cap
    return b if end > b else end


def _percentile(values: List[timedelta], q: float) -> timedelta:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1) + 0.5))]


def open_caps(jobs: List[dict]) -> Dict[tuple, timedelta]:
    """{(stage, modality): cap} and {(stage, None): pooled cap}, from the
    finished waits: 95th percentile, clamped to OPEN_MIN..OPEN_MAX."""
    clamp = lambda td: max(OPEN_MIN, min(OPEN_MAX, td))
    caps = {}
    for stage in ('exam', 'report'):
        waits = {}
        for j in jobs:
            iv = j[stage]
            if iv and iv[1] is not None:
                waits.setdefault(j['modality'], []).append(iv[1] - iv[0])
        pooled = [w for ws in waits.values() for w in ws]
        caps[(stage, None)] = clamp(_percentile(pooled, 0.95)) if len(pooled) >= OPEN_SAMPLES else OPEN_MAX
        for m, ws in waits.items():
            if len(ws) >= OPEN_SAMPLES:
                caps[(stage, m)] = clamp(_percentile(ws, 0.95))
    return caps


def apply_caps(jobs: List[dict], caps: Dict[tuple, timedelta]) -> None:
    """Give each open stage its modality's cap: (start, None, cap)."""
    for j in jobs:
        for stage in ('exam', 'report'):
            iv = j[stage]
            if iv and iv[1] is None:
                cap = caps.get((stage, j['modality'])) or caps.get((stage, None)) or OPEN_MAX
                j[stage] = (iv[0], None, cap)


def _overlap(iv, a: datetime, b: datetime) -> timedelta:
    start, end, cap = _parts(iv)
    end = _open_end(start, end, b, cap)
    start = a if start < a else start
    return end - start if end > start else timedelta(0)


def _busy(intervals, a: datetime, b: datetime) -> timedelta:
    """Length of the union of the intervals within [a, b]."""
    spans = []
    for iv in intervals:
        start, end, cap = _parts(iv)
        end = _open_end(start, end, b, cap)
        start = a if start < a else start
        if end > start:
            spans.append((start, end))
    spans.sort()
    total = timedelta(0)
    cur_s = cur_e = None
    for s, e in spans:
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        elif e > cur_e:
            cur_e = e
    if cur_e is not None:
        total += cur_e - cur_s
    return total


def stage_stats(intervals, a: datetime, b: datetime) -> dict:
    """lam, x, L, W, little and busy for one stage over [a, b]."""
    span_h = _hours(b - a)
    if span_h <= 0:
        return {'lam': 0.0, 'x': 0.0, 'L': 0.0, 'W': None, 'little': None, 'busy': 0.0, 'n_in': 0, 'n_out': 0}
    n_in = sum(1 for iv in intervals if a < iv[0] <= b)
    done = [(iv[0], iv[1]) for iv in intervals if iv[1] is not None and a < iv[1] <= b]
    area_h = sum(_hours(_overlap(iv, a, b)) for iv in intervals)
    lam = n_in / span_h
    W = (sum((e - s).total_seconds() for s, e in done) / 60.0 / len(done)) if done else None
    return {
        'lam': round(lam, 2),
        'x': round(len(done) / span_h, 2),
        'L': round(area_h / span_h, 2),
        'W': round(W, 1) if W is not None else None,
        'little': round(lam * W / 60.0, 2) if W is not None else None,
        'busy': round(_hours(_busy(intervals, a, b)) / span_h, 3),
        'n_in': n_in,
        'n_out': len(done),
    }


def service_samples(jobs: List[dict]) -> List[tuple]:
    """(start, end) of each exam the room was busy with, from the PACS start
    and the written report.

    The PACS gives no end time, but an ultrasound exam ends with its report
    and the next one normally starts only after it, so the end is the report
    validation; and whenever the next exam starts the previous one is over
    (end = min(report, next start)). Rules:
      * report at/after the start: end = report, unless the next exam started
        first (a late or forgotten report): then end = next start, only valid
        when that next request was already waiting (else the gap holds idle
        time);
      * no report time: end = next start, same waiting condition;
      * none known, or an exam longer than SERVICE_MAX: no sample.
    One room is assumed; another room's exams only lengthen the estimate."""
    started = sorted((j for j in jobs if j['t_start']), key=lambda j: j['t_start'])
    out = []
    for i, cur in enumerate(started):
        start, rep = cur['t_start'], cur['t_rep']
        nxt = started[i + 1] if i + 1 < len(started) else None
        next_ok = nxt is not None and nxt['t_req'] <= start
        end = None
        if rep is not None and rep > start:
            if nxt is not None and nxt['t_start'] < rep:
                end = nxt['t_start'] if next_ok else None
            else:
                end = rep
        elif rep is None and next_ok:
            end = nxt['t_start']
        if end is not None and timedelta(0) < end - start <= SERVICE_MAX:
            out.append((start, end))
    return out


def service_stats(samples: List[tuple], a: datetime, b: datetime) -> dict:
    """Exams that ended in (a, b]: count, mean and median minutes; and the
    share of [a, b] the room was occupied (union of the exams)."""
    done = [(s, e) for s, e in samples if a < e <= b]
    span_h = _hours(b - a)
    occ = round(_hours(_busy(samples, a, b)) / span_h, 3) if span_h > 0 else 0.0
    if not done:
        return {'n': 0, 'mean': None, 'median': None, 'occupancy': occ}
    vals = sorted((e - s).total_seconds() / 60.0 for s, e in done)
    mid = len(vals) // 2
    med = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2.0
    return {'n': len(vals), 'mean': round(sum(vals) / len(vals), 1), 'median': round(med, 1),
            'occupancy': occ}


def service_rate(intervals, a: datetime, b: datetime, window: timedelta = timedelta(hours=1),
                 step: timedelta = timedelta(minutes=10), q: float = 0.9) -> Optional[float]:
    """Demonstrated capacity: the q-th percentile of the departures in a
    rolling window over [a, b], per hour. Hipocrate records no service
    times, and departures per busy hour fails where someone is nearly
    always waiting (it is then the mean throughput, far below what the room
    does in its good hours). The percentile, not the max, so one batch of
    exams marked done at once does not set the capacity. None when nothing
    left in that share of the windows."""
    ends = sorted(iv[1] for iv in intervals if iv[1] is not None and a - window < iv[1] <= b)
    if not ends:
        return None
    counts = []
    t = a + window
    while t <= b:
        lo = t - window
        counts.append(sum(1 for e in ends if lo < e <= t))
        t += step
    if not counts:
        return None
    counts.sort()
    per_h = counts[min(len(counts) - 1, int(q * (len(counts) - 1) + 0.5))] / _hours(window)
    return round(per_h, 2) if per_h > 0 else None


def _segment(jobs, as_of, span_start, window, samples=()) -> dict:
    exam = [j['exam'] for j in jobs if j['exam']]
    report = [j['report'] for j in jobs if j['report']]
    w_start = as_of - window
    cur = stage_stats(exam, w_start, as_of)
    cur_r = stage_stats(report, w_start, as_of)
    span = stage_stats(exam, span_start, as_of)
    span_r = stage_stats(report, span_start, as_of)
    mu = service_rate(exam, span_start, as_of)
    mu_r = service_rate(report, span_start, as_of)
    # With enough estimated durations the utilisation is the offered load
    # lam * E[S] (and mu = 1 / E[S]) instead of the demonstrated-capacity guess.
    svc_cur = service_stats(samples, w_start, as_of)
    svc_span = service_stats(samples, span_start, as_of)
    mean_h = svc_span['mean'] / 60.0 if svc_span['n'] >= SERVICE_MIN_SAMPLES and svc_span['mean'] else None
    service = {'occupancy': svc_cur['occupancy'], 'n_span': svc_span['n'],
               'mean_span': svc_span['mean'], 'median_span': svc_span['median'],
               'mu': round(1.0 / mean_h, 2) if mean_h else None,
               'rho': round(cur['lam'] * mean_h, 2) if mean_h else None}
    door = [(j['t_req'] - j['t_arr']).total_seconds() / 60.0
            for j in jobs if j['t_arr'] and w_start < j['t_req'] <= as_of]
    door_span = [(j['t_req'] - j['t_arr']).total_seconds() / 60.0
                 for j in jobs if j['t_arr'] and span_start < j['t_req'] <= as_of]
    return {
        'exam': {**cur, 'mu': mu, 'rho': round(cur['lam'] / mu, 2) if mu else None},
        'report': {**cur_r, 'mu': mu_r, 'rho': round(cur_r['lam'] / mu_r, 2) if mu_r else None},
        'span': {'exam': {**span, 'mu': mu}, 'report': {**span_r, 'mu': mu_r}},
        'service': service,
        'upu_door_W': round(sum(door) / len(door), 1) if door else None,
        'upu_door_W_span': round(sum(door_span) / len(door_span), 1) if door_span else None,
    }


def compute(rows: List[dict], report_times: Dict[str, Optional[datetime]],
            arrivals: Dict[str, Optional[datetime]], as_of: datetime,
            hours: int = 24, window_min: int = 60, step_min: int = 10,
            truncated: bool = False, pacs_studies: Optional[Dict[str, list]] = None) -> dict:
    jobs = build_jobs(rows, report_times, arrivals, pacs_studies)
    caps = open_caps(jobs)
    apply_caps(jobs, caps)
    window = timedelta(minutes=window_min)
    span_start = as_of - timedelta(hours=hours)

    current = _segment(jobs, as_of, span_start, window, service_samples(jobs))

    exam = [j['exam'] for j in jobs if j['exam']]
    report = [j['report'] for j in jobs if j['report']]
    # rho per point: lam of that point's hour over the span's capacity (the
    # measured 1/E[S] when there is one, else the demonstrated p90 one)
    mu_eff = current['service']['mu'] or current['exam']['mu']
    samples = service_samples(jobs)
    series = []
    t = span_start + timedelta(minutes=step_min)
    while t <= as_of:
        e = stage_stats(exam, t - window, t)
        rho_t = round(e['lam'] / mu_eff, 2) if mu_eff else None
        st = strain_index.strain(t, rho_t, e['L'], e['W'], samples, current['service']['median_span'], window)
        series.append({
            't': t.strftime('%Y-%m-%dT%H:%M'),
            'lam': e['lam'], 'x': e['x'], 'L': e['L'], 'W': e['W'],
            'rho': rho_t,
            'strain': st['index'], 'strain_c': st['c'],
        })
        t += timedelta(minutes=step_min)

    def relevant(j):
        # requested in the span, or its exam stage reaches into it; an open
        # one only until its cap (a stale row is not a job of this span)
        if span_start < j['t_req'] <= as_of:
            return True
        iv = j['exam']
        if not iv:
            return False
        end = iv[1] if iv[1] is not None else iv[0] + _parts(iv)[2]
        return end > span_start

    in_span = [j for j in jobs if relevant(j)]
    left = [j for j in in_span if j['left'] and not j['inconsistent']]
    upu = [j for j in in_span if j['upu']]
    coverage = {
        'jobs': len(in_span),
        'exam_times': {'known': sum(1 for j in left if j['exam_known']), 'of': len(left)},
        'report_times': {'known': sum(1 for j in left if j['report_known']), 'of': len(left)},
        'pacs_start': {'known': sum(1 for j in left if j['pacs_start']), 'of': len(left)},
        'inconsistent': sum(1 for j in in_span if j['inconsistent']),
        'upu_arrivals': {'known': sum(1 for j in upu if j['t_arr']), 'of': len(upu)},
        # open past their cap at as_of: left out of the queue
        'stale': {stage: sum(1 for j in jobs if j[stage] and j[stage][1] is None
                             and j[stage][0] + j[stage][2] < as_of)
                  for stage in ('exam', 'report')},
    }

    return {
        'as_of': as_of.strftime('%Y-%m-%dT%H:%M'),
        'span_h': hours,
        'window_min': window_min,
        'step_min': step_min,
        'scope': {'modality': SCOPE_MODALITY, 'section': SCOPE_SECTION},
        'current': current,
        'series': series,
        'coverage': coverage,
        'truncated': truncated,
        'open_caps_h': {f"{stage}:{m or 'all'}": round(_hours(cap), 2) for (stage, m), cap in caps.items()},
    }
