"""Queue-theory metrics for the Schedule tab (GET /api/schedule/queue).

Pure computation: no aiohttp, no Hipocrate. The handler in hippobridge.py
fetches the schedule rows and the cache-only times (report validation, UPU
presentation) and hands them here. Nothing is stored; every call recomputes
from the timestamps, so any past moment can be analysed as well as now.

Scope. The exam queue is the ultrasound requests from UPU (2026-11-11,
owner's call: one server, so one queue and a meaningful rho; in_scope()):
the only one where a patient waits for the radiologist. Since 2026-11-14
the on-call shift is seen whole: every other report (X-ray, CT, RF, MRI
from UPU or a ward, ward ultrasound) is a *read* (build_reads()). On-call
work is told by who validated it and when, not by the section: the on-call
team (on_call_team()) is whoever validates reports in the on-call hours.
Reads have no measured length: each is the time since that radiologist's
previous report, capped by a typical length (read_work()). UPU reads, and
ward ones the team validated, wait in a second, reading queue (exam done ->
report validated).

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

import bisect
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

import strain as strain_index

SCOPE_MODALITY = 'eco'   # ultrasound
SCOPE_LAB_ID = '28'      # its Hipocrate laboratory (HippoClientSchedule._LAB_ID_TO_MODALITY)
SCOPE_SECTION = 'UPU'
# Every laboratory whose reports the on-call team may validate (the handler
# fetches one listing each); interventional radiology is left out.
SCOPE_LABS = {'eco': '28', 'radio': '49', 'ct': '26', 'fluoro': '50', 'irm': '32'}
MODALITY_LABEL = {'eco': 'us', 'radio': 'xr', 'ct': 'ct', 'fluoro': 'rf', 'irm': 'mr'}
# Minutes of work per study of a read, when the gap since the radiologist's
# previous report is longer (assumptions; seen 6-12 Nov 2026 on call: an
# X-ray report follows the previous one by a median 2 min, a CT by 22).
# A ward ultrasound takes the median measured UPU exam.
READ_TYPICAL = {'radio': timedelta(minutes=3), 'ct': timedelta(minutes=25),
                'fluoro': timedelta(minutes=15), 'irm': timedelta(minutes=30)}
READ_MIN = timedelta(minutes=1)       # a report validated the same minute as the previous one
TEAM_MIN_REPORTS = 5                  # reports in the on-call hours that make a team member
TEAM_GRACE = timedelta(minutes=30)    # the day staff's last reports, just after the handover
SHIFT_HIGH = 65                       # strain from which a point counts in a shift's hours_high
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
MAX_SPAN_H = 96   # longest explicit ?start=..&end=.. span
# PACS study start (pacs.py: StudyTime). Hipocrate records no exam start, the
# modality's MPPS is not available, and the PACS returns no per-image times
# (checked live 2026-11-12: image/series-level C-FIND repeats StudyTime
# only), so the end of an exam is unknown; it is taken from the written report
# (an ultrasound exam ends with it) or the next exam's start (service_samples()).
PACS_SLACK = timedelta(minutes=15)    # a study may start a little before the request is entered
# An exam is call, preparation, scan, talk, discharge and the written report,
# done one at a time (owner, 2026-11-12); a longer start-to-report is a late
# report with idle time in it, not one exam.
SERVICE_MAX = timedelta(minutes=60)
TYPICAL_EXAM = timedelta(minutes=8)   # an exam's length when none was measured
REGION_MIN_SAMPLES = 3                # exams of a kind needed for its own median length
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


def study_key(study: dict) -> Optional[str]:
    """A PACS study's identity: its UID, else its start."""
    return study.get('uid') or (str(study.get('start')) if study.get('start') else None)


def pick_study(studies, t_req: datetime, t_perf: Optional[datetime] = None) -> Optional[datetime]:
    found = pick_study_entry(studies, t_req, t_perf)
    return found[0] if found else None


def pick_study_entry(studies, t_req: datetime, t_perf: Optional[datetime] = None):
    """Start of the PACS study that belongs to this request.

    `studies` are the same-patient, same-modality studies the PACS returned
    (dicts with an ISO 'start'). A candidate starts no earlier than
    PACS_SLACK before the request and no later than OPEN_MAX after it; with a
    performed_at the nearest one wins, else the earliest. The start is
    clamped to the request time (an exam cannot wait a negative time).
    Returns (start, study_key) or None when none fits."""
    cands = []
    for st in studies or []:
        a = parse_ts(st.get('start'))
        if a is not None and t_req - PACS_SLACK <= a <= t_req + OPEN_MAX:
            cands.append((a, study_key(st)))
    if not cands:
        return None
    start, key = min(cands, key=(lambda c: abs(c[0] - t_perf)) if t_perf else (lambda c: c[0]))
    return max(start, t_req), key


def build_jobs(rows: List[dict], report_times: Dict[str, Optional[datetime]],
               arrivals: Dict[str, Optional[datetime]],
               pacs_studies: Optional[Dict[str, list]] = None) -> List[dict]:
    """One job per imaging row, with each stage as an interval [start, end)
    (end None = still waiting), or None when the stage is unknown/not reached.

    With a PACS study the exam stage ends when the exam *starts* (the patient
    leaves the queue for the room) and a `service` stage (start, end) exists;
    the report stage starts at the exam's end. Without one, performed_at
    stands for all of it, as before.

    Two requests of one patient matched to the same PACS study (two exams
    asked at once, done as one) are one patient in one exam: the later
    request is `merged` and left out of both stages (counted in coverage)."""
    pacs_studies = pacs_studies or {}
    jobs = []
    claimed = set()
    order = lambda r: parse_ts(r.get('date_time')) or datetime.max
    for r in sorted(rows, key=order):
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

        t_start = key = None
        if not inconsistent:
            found = pick_study_entry(pacs_studies.get(rid), t_req, t_perf)
            if found:
                t_start, key = found
        merged = key is not None and key in claimed
        if merged:
            t_start = t_exam = None
        elif key is not None:
            claimed.add(key)
        # the wait ends when the exam starts (PACS), else at performed_at
        t_left = t_start or t_exam
        t_out = t_exam or t_start            # the exam is over: the report stage starts

        exam = None
        if inconsistent or merged:
            pass
        elif t_left is not None:
            exam = (t_req, t_left)
        elif not left:
            exam = (t_req, None)

        report = None
        if inconsistent or merged:
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
            'study_key': None if merged else key,
            't_rep': t_rep,
            't_perf': None if inconsistent or merged else t_perf,
            'inconsistent': inconsistent,
            'merged': merged,
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


def _pct(values: List[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1) + 0.5))]


def _percentile(values: List[timedelta], q: float) -> timedelta:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1) + 0.5))]


def open_caps(jobs: List[dict], stages=('exam', 'report')) -> Dict[tuple, timedelta]:
    """{(stage, modality): cap} and {(stage, None): pooled cap}, from the
    finished waits: 95th percentile, clamped to OPEN_MIN..OPEN_MAX."""
    clamp = lambda td: max(OPEN_MIN, min(OPEN_MAX, td))
    caps = {}
    for stage in stages:
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


def apply_caps(jobs: List[dict], caps: Dict[tuple, timedelta], stages=('exam', 'report')) -> None:
    """Give each open stage its modality's cap: (start, None, cap)."""
    for j in jobs:
        for stage in stages:
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
    """(start, end) of each UPU exam, from the PACS start and the written report.

    The PACS gives no end time, but an ultrasound exam is done one at a time
    and ends with its written report: nothing else starts before it (owner,
    2026-11-12). So the end is the report validation, and whenever the next
    exam starts the previous one is over (end = min(report, next start)):
      * report at/after the start: end = report, unless the next exam started
        first (a late or forgotten report, the rare exception): then end =
        next start, only valid when that next request was already waiting
        (else the gap may hold idle time);
      * no report time: end = next start, same condition;
      * none known, or an exam longer than SERVICE_MAX: no sample.
    In the day shift two radiologists may scan UPU patients at once; the
    next start then cuts an exam short, so daytime lengths read low."""
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


def work_intervals(jobs: List[dict], samples: List[tuple], typical: timedelta) -> List[tuple]:
    """(job, (start, end)) of every UPU exam done, for the accumulated work:
    the measured exam (service_samples()); a PACS start without a measured
    end: `typical` long, cut at the next start; no PACS start at all (the
    patient's CNP not cached): `typical` long, ending at the report, else at
    the performed time."""
    measured = dict(samples)
    starts = sorted(j['t_start'] for j in jobs if j['t_start'])
    out = []
    for j in jobs:
        if j['merged'] or j['inconsistent']:
            continue
        s = j['t_start']
        if s is not None:
            if s in measured:
                out.append((j, (s, measured[s])))
                continue
            i = bisect.bisect_right(starts, s)
            end = min(s + typical, starts[i]) if i < len(starts) else s + typical
            out.append((j, (s, end)))
        elif j['left']:
            end = j['t_rep'] or j['t_perf']
            if end is not None:
                out.append((j, (end - typical, end)))
    return out


def norm_name(value) -> Optional[str]:
    """A validator's name, compared case- and space-insensitively."""
    v = ' '.join(str(value or '').split()).casefold()
    return v or None


def on_call_from(block_start: datetime) -> datetime:
    """When the on-call team takes the UPU over: weekdays 14:00, weekends at
    the block's start (08:00). Holidays are not known."""
    return block_start + timedelta(hours=6 if block_start.weekday() < 5 else 0)


def in_on_call(t: datetime) -> bool:
    """t falls in the on-call hours of its duty block."""
    return t >= on_call_from(strain_index.duty_start(t))


def on_call_team(events: List[dict], block_start: datetime, until: datetime) -> set:
    """The radiologists on call in the duty block starting at block_start:
    whoever validated TEAM_MIN_REPORTS reports or more, of any modality and
    section, in its on-call hours (one or two people; the day staff's last
    few reports right after the handover do not make them on call). Until
    someone has that many, whoever validated one later than TEAM_GRACE after
    the handover. Empty when nobody has. `events` have 'validator' and
    't_rep'. The names never leave compute()."""
    frm, end = on_call_from(block_start), min(block_start + timedelta(days=1), until)
    counts: Dict[str, int] = {}
    late = set()
    for e in events:
        v, t = e['validator'], e['t_rep']
        if v and t and frm <= t < end:
            counts[v] = counts.get(v, 0) + 1
            if t >= frm + TEAM_GRACE:
                late.add(v)
    return {v for v, n in counts.items() if n >= TEAM_MIN_REPORTS} or late


def on_call_radiologist(jobs: List[dict], block_start: datetime, until: datetime,
                        team: Optional[set] = None) -> Optional[str]:
    """The senior on call in the duty block starting at block_start: the
    validator of most reports (any modality) between 20:00 and 02:00, the
    busiest hours, which the senior takes (owner, 2026-11-12); before 20:00,
    the most in the on-call hours so far. Alone on call, that is the one
    radiologist. Only `team` members when given. None before anyone has
    validated one. Used only to tell the senior's rest from the team's work:
    never returned, never logged."""
    end = min(block_start + timedelta(days=1), until)
    windows = [(block_start + timedelta(hours=12), min(block_start + timedelta(hours=18), end)),
               (on_call_from(block_start), end)]
    for frm, to in windows:
        counts: Dict[str, int] = {}
        for j in jobs:
            if j['validator'] and j['t_rep'] and frm <= j['t_rep'] < to and (not team or j['validator'] in team):
                counts[j['validator']] = counts.get(j['validator'], 0) + 1
        if counts:
            return max(sorted(counts), key=lambda k: counts[k])
    return None


def build_reads(rows: List[dict], report_times: Dict[str, Optional[datetime]],
                validators: Optional[Dict[str, str]] = None,
                counts: Optional[Dict[str, int]] = None) -> List[dict]:
    """One read per imaging row outside the exam queue (X-ray, CT, RF, MRI of
    any section; ward ultrasound): images done at t_perf, report validated at
    t_rep by `validator`, `n` studies. A performed time before the request
    is a glitch: unknown."""
    validators, counts = validators or {}, counts or {}
    out = []
    for r in rows:
        if (r.get('modality') not in SCOPE_LABS or r.get('status') in EXCLUDED_STATUSES or in_scope(r)):
            continue
        t_req = parse_ts(r.get('date_time'))
        if t_req is None:
            continue
        rid = str(r.get('request_id') or '')
        t_perf = parse_performed(r.get('performed_at'))
        if t_perf is not None and t_perf < t_req:
            t_perf = None
        try:
            n = max(1, int(counts.get(rid) or r.get('analysis_count') or 1))
        except (TypeError, ValueError):
            n = 1
        out.append({
            'id': rid,
            'modality': r.get('modality'),
            'upu': (r.get('section') or '').strip().upper() == SCOPE_SECTION,
            'left': r.get('status') in LEFT_STATUSES,
            't_req': t_req,
            't_perf': t_perf,
            't_rep': report_times.get(rid),
            'validator': norm_name(validators.get(rid)),
            'n': n,
            'read': None,     # its interval in the reading queue (reading_queue())
        })
    return out


def read_length(read: dict, typical: timedelta) -> timedelta:
    """The most a read's work takes: its modality's typical length per study."""
    return READ_TYPICAL.get(read['modality'], typical) * read['n']


def read_work(reads: List[dict], work: List[tuple], typical: timedelta) -> List[tuple]:
    """(read, (start, end)) of every validated read: the work it took.

    Nothing records when a radiologist opens a study, only when the report is
    validated (to the minute). So per radiologist, in the order of their
    reports (their UPU ultrasound exams, `work`, included): a read ends at
    its validation and starts at the latest of: its typical length before
    (read_length()), the end of that radiologist's previous report, and the
    moment the images existed. X-rays read in a batch then cost what they
    took, a CT after a pause its typical length. Never under READ_MIN."""
    lines: Dict[str, list] = {}
    for j, (s, e) in work:
        if j.get('validator'):
            lines.setdefault(j['validator'], []).append((e, 0, None))
    for rd in reads:
        if rd['validator'] and rd['t_rep']:
            lines.setdefault(rd['validator'], []).append((rd['t_rep'], 1, rd))
    out = []
    for line in lines.values():
        prev = None
        for end, _, rd in sorted(line, key=lambda x: (x[0], x[1])):
            if rd is not None:
                start = end - read_length(rd, typical)
                if prev is not None and prev > start:
                    start = prev
                if rd['t_perf'] is not None and start < rd['t_perf'] < end:
                    start = rd['t_perf']
                if end - start < READ_MIN:
                    start = end - READ_MIN
                out.append((rd, (start, end)))
            prev = end if prev is None or end > prev else prev
    return out


def reading_queue(reads: List[dict], team_of) -> None:
    """Set each read's interval in the reading queue, exam done -> report
    validated (None: not in it):
      * a UPU read: from t_perf to its report; still open when performed and
        not reported; unknown (out) when the row has left with no cached
        report time, or was never performed;
      * a ward read: only when an on-call team member validated it in the
        on-call hours (`team_of(block_start)`), and from the handover at the
        earliest. One left for the day staff is not the shift's."""
    for rd in reads:
        s, e = rd['t_perf'], rd['t_rep']
        rd['read'] = None
        if s is None:
            continue
        if rd['upu']:
            if e is not None:
                if e >= s:
                    rd['read'] = (s, e)
            elif not rd['left']:
                rd['read'] = (s, None)
        elif e is not None and rd['validator'] and in_on_call(e):
            block = strain_index.duty_start(e)
            if rd['validator'] in team_of(block):
                s = max(s, on_call_from(block))
                if e >= s:
                    rd['read'] = (s, e)


def _median_td(samples: List[tuple]) -> Optional[timedelta]:
    if not samples:
        return None
    vals = sorted(e - s for s, e in samples)
    return vals[len(vals) // 2]


def service_stats(samples: List[tuple], a: datetime, b: datetime, busy: Optional[List[tuple]] = None) -> dict:
    """Exams that ended in (a, b]: count, mean and median minutes; and the
    share of [a, b] a UPU exam was running (union of `busy`, every UPU exam
    done; the samples alone when not given)."""
    done = [(s, e) for s, e in samples if a < e <= b]
    span_h = _hours(b - a)
    occ = round(_hours(_busy(busy if busy is not None else samples, a, b)) / span_h, 3) if span_h > 0 else 0.0
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


def region_key(regions: Optional[List[str]]) -> str:
    """The kind of exam: its regions, sorted ('abdomen+pelvis'); '' unknown."""
    return '+'.join(sorted({r for r in (regions or []) if r and r != 'unknown'}))


def relative_lengths(samples: List[tuple], jobs: List[dict],
                     regions: Dict[str, List[str]]) -> List[tuple]:
    """((start, end), length / median length of the same kind of exam): the
    region's median with REGION_MIN_SAMPLES of them, else all exams'."""
    kind = {j['t_start']: region_key(regions.get(j['id'])) for j in jobs if j['t_start']}
    mins = lambda s, e: (e - s).total_seconds() / 60.0
    by_kind: Dict[str, List[float]] = {}
    for s, e in samples:
        by_kind.setdefault(kind.get(s, ''), []).append(mins(s, e))
    every = [m for ms in by_kind.values() for m in ms]
    if not every:
        return []
    median = lambda ms: sorted(ms)[len(ms) // 2]
    overall = median(every)
    out = []
    for s, e in samples:
        ms = by_kind.get(kind.get(s, ''), [])
        ref = median(ms) if kind.get(s) and len(ms) >= REGION_MIN_SAMPLES else overall
        if ref > 0:
            out.append(((s, e), mins(s, e) / ref))
    return out


def strain_refs(stats: List[dict], read_L: Iterable[float] = (),
                read_oldest: Iterable[Optional[float]] = ()) -> 'strain_index.Refs':
    """People waiting are judged against this queue's own busy hours (the
    span's 90th percentile of the hourly L and W), never below the floors;
    the same for the studies waiting to be read and the oldest of them."""
    Ls = [e['L'] for e in stats if e['L']]
    Ws = [e['W'] for e in stats if e['W'] is not None]
    Rs = [v for v in read_L if v]
    Os = [v for v in read_oldest if v]
    ref = lambda vals, floor: max(floor, _pct(vals, 0.9)) if vals else floor
    return strain_index.Refs(
        queue=ref(Ls, strain_index.QUEUE_REF), wait=ref(Ws, strain_index.WAIT_REF_MIN),
        read_queue=ref(Rs, strain_index.READ_QUEUE_REF), read_oldest=ref(Os, strain_index.READ_OLDEST_REF))


def oldest_wait(exam_intervals, t: datetime) -> Optional[float]:
    """Minutes the longest-waiting patient has waited at t (None: nobody)."""
    ages = []
    for iv in exam_intervals:
        start, end, cap = _parts(iv)
        end = end if end is not None else start + cap
        if start <= t < end:
            ages.append((t - start).total_seconds() / 60.0)
    return round(max(ages), 1) if ages else None


def idle_while_waiting(exam_intervals, busy_merged: List[tuple], a: datetime, b: datetime) -> float:
    """Share of [a, b] with someone waiting and the room idle, not counting
    the first CALL_ALLOWANCE of each idle gap (calling and preparing the
    next patient). |idle ∩ waiting| = |idle| + |waiting| - |idle ∪ waiting|."""
    allowance = strain_index.CALL_ALLOWANCE
    idle, cursor = [], None
    for s, e in busy_merged:
        if e <= a - allowance:
            cursor = e
            continue
        if s >= b:
            break
        gap_start = cursor if cursor is not None else a - allowance
        if s > gap_start:
            idle.append((gap_start + allowance, s))
        cursor = e
    gap_start = cursor if cursor is not None else a - allowance
    if b > gap_start:
        idle.append((gap_start + allowance, b))
    idle = [(max(s, a), min(e, b)) for s, e in idle if min(e, b) > max(s, a)]
    if not idle:
        return 0.0
    both = _hours(_busy(idle, a, b)) + _hours(_busy(exam_intervals, a, b)) - _hours(_busy(idle + list(exam_intervals), a, b))
    return round(max(0.0, both) / _hours(b - a), 3)


def _segment(jobs, as_of, span_start, window, samples=(), busy=None) -> dict:
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
    svc_cur = service_stats(samples, w_start, as_of, busy)
    svc_span = service_stats(samples, span_start, as_of, busy)
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
            truncated: bool = False, pacs_studies: Optional[Dict[str, list]] = None,
            regions: Optional[Dict[str, List[str]]] = None,
            validators: Optional[Dict[str, str]] = None,
            counts: Optional[Dict[str, int]] = None,
            now: Optional[datetime] = None) -> dict:
    """`rows`: the schedule rows of every imaging lab; the UPU ultrasound
    ones make the exam queue, the rest are reads.
    `regions`: the regions of each request's studies (from its report
    page), so an exam's length is compared with the same kind of exam.
    `validators`: who validated each request's report, so the on-call team
    and its senior are found (on_call_team(), on_call_radiologist()): the
    team's work in every modality accumulates, the senior's own gaps are the
    rest; the names stay inside this function.
    `counts`: the validated studies of each request (a read's length).
    `now`: the real present when as_of is in the past (default as_of): a
    read still unreported now, long past its cap, was never going to be
    read (about 5 % of the X-rays stay unreported), so it never waited."""
    jobs = build_jobs(rows, report_times, arrivals, pacs_studies)
    validators = validators or {}
    for j in jobs:
        j['validator'] = norm_name(validators.get(j['id']))
    reads = build_reads(rows, report_times, validators, counts)
    events = jobs + reads
    caps = open_caps(jobs)
    apply_caps(jobs, caps)
    window = timedelta(minutes=window_min)
    span_start = as_of - timedelta(hours=hours)

    samples = service_samples(jobs)
    typical = _median_td(samples) or TYPICAL_EXAM
    work = work_intervals(jobs, samples, typical)
    busy = [iv for _, iv in work]
    reading = read_work(reads, work, typical)

    # Each duty block: its team, its senior, the team's work in every
    # modality (the accumulated work) and the senior's own (whose gaps are
    # the rest). Built on demand, also for the blocks before the span.
    blocks: Dict[datetime, dict] = {}

    def block_at(start: datetime) -> dict:
        if start in blocks:
            return blocks[start]
        frm, until = on_call_from(start), min(start + timedelta(days=1), as_of)
        team = on_call_team(events, start, as_of)
        who = on_call_radiologist(events, start, as_of, team)
        us = [(j, iv) for j, iv in work if iv[1] > frm]
        us_in = [(j, iv) for j, iv in us if iv[0] < until]
        rd_in = [(rd, iv) for rd, iv in reading if rd['validator'] in team and frm <= iv[1] < start + timedelta(days=1)]
        reports = {label: 0 for label in MODALITY_LABEL.values()}
        reports['us'] = len(us_in)
        for rd, iv in rd_in:
            if iv[1] <= until:
                reports[MODALITY_LABEL[rd['modality']]] += 1
        blocks[start] = {
            'team_names': team,
            # the team's work: every UPU ultrasound since the handover and the team's reads
            'busy': [iv for _, iv in us] + [iv for _, iv in rd_in],
            'reads': [iv for _, iv in rd_in],
            'own': ([iv for j, iv in work if j['validator'] == who]
                    + [iv for rd, iv in reading if rd['validator'] == who]) if who else None,
            'known': who is not None,
            'team': len(us_in),
            'senior': sum(1 for j, _ in us_in if who and j['validator'] == who),
            'radiologists': len(team) or len({j['validator'] for j, _ in us_in if j['validator']}),
            'reports': reports,
            'ward': sum(1 for rd, iv in rd_in if not rd['upu'] and iv[1] <= until),
        }
        return blocks[start]

    reading_queue(reads, lambda start: block_at(start)['team_names'])
    read_caps = open_caps(reads, ('read',))
    apply_caps(reads, read_caps, ('read',))
    caps.update(read_caps)
    seen_at = max(now or as_of, as_of)
    never_read = 0
    for rd in reads:
        iv = rd['read']
        if iv and iv[1] is None and iv[0] + iv[2] < seen_at:
            rd['read'] = None
            never_read += 1

    current = _segment(jobs, as_of, span_start, window, samples, busy)
    read_ivs = [rd['read'] for rd in reads if rd['read']]
    w_start = as_of - window
    cur_read = stage_stats(read_ivs, w_start, as_of)
    current['reading'] = {**cur_read, 'now': sum(1 for iv in read_ivs if _waiting(iv, as_of)),
                          'oldest': oldest_wait(read_ivs, as_of),
                          'span': stage_stats(read_ivs, span_start, as_of)}

    exam = [j['exam'] for j in jobs if j['exam']]
    report = [j['report'] for j in jobs if j['report']]
    # rho per point: the work offered in that point's hour, in radiologist
    # hours per hour. Ultrasound: lam of the hour over the span's capacity
    # (the measured 1/E[S] when there is one, else the demonstrated p90 one);
    # reads: the minutes of work of the studies done in the hour.
    mu_eff = current['service']['mu'] or current['exam']['mu']
    measured = {id(rd): iv[1] - iv[0] for rd, iv in reading}
    offered = sorted(((rd['read'][0], _hours(measured.get(id(rd)) or read_length(rd, typical)))
                      for rd in reads if rd['read']), key=lambda x: x[0])
    offered_t = [t for t, _ in offered]
    offered_sum = [0.0]
    for _, h in offered:
        offered_sum.append(offered_sum[-1] + h)

    def read_load(a: datetime, b: datetime) -> float:
        lo, hi = bisect.bisect_right(offered_t, a), bisect.bisect_right(offered_t, b)
        return (offered_sum[hi] - offered_sum[lo]) / _hours(b - a)

    points = []
    t = span_start + timedelta(minutes=step_min)
    while t <= as_of:
        points.append((t, stage_stats(exam, t - window, t), stage_stats(read_ivs, t - window, t)['L'],
                       oldest_wait(read_ivs, t)))
        t += timedelta(minutes=step_min)
    refs = strain_refs([e for _, e, _, _ in points], [r for _, _, r, _ in points], [o for _, _, _, o in points])
    relative = relative_lengths(samples, jobs, regions or {})
    # the requests the exam queue counts (the same ones as its lambda)
    arrivals = sorted(j['t_req'] for j in jobs if j['exam'])
    # the room is not idle while the team reads an X-ray or a CT
    team_reads = [iv for start in sorted({strain_index.duty_start(t) for t, _, _, _ in points})
                  for iv in block_at(start)['reads']]
    busy_merged = strain_index.merge(busy + team_reads)

    series = []
    for t, e, read_L, read_old in points:
        rho_us = e['lam'] / mu_eff if mu_eff else None
        rho_read = read_load(t - window, t)
        rho_t = round((rho_us or 0.0) + rho_read, 2) if rho_us is not None or rho_read else None
        idle_w = idle_while_waiting(exam, busy_merged, t - window, t)
        blk = block_at(strain_index.duty_start(t))
        st = strain_index.score(strain_index.Moment(
            t=t, rho=rho_t, queue=e['L'], wait=e['W'], oldest=oldest_wait(exam, t),
            idle_waiting=idle_w, busy=blk['busy'], own=blk['own'], arrivals=arrivals, capacity=mu_eff,
            relative=[r for (s0, e0), r in relative if t - window < e0 <= t],
            read_queue=read_L, read_oldest=read_old), refs)
        series.append({
            't': t.strftime('%Y-%m-%dT%H:%M'),
            'lam': e['lam'], 'x': e['x'], 'L': e['L'], 'W': e['W'],
            'rho': rho_t, 'rho_read': round(rho_read, 2),
            'read_L': read_L, 'read_oldest': read_old,
            'idle_waiting': round(idle_w, 2), 'on_call_known': blk['known'],
            'strain': st['index'], 'strain_c': st['c'],
        })

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
    left = [j for j in in_span if j['left'] and not j['inconsistent'] and not j['merged']]
    upu = [j for j in in_span if j['upu']]
    reads_span = [rd for rd in reads if span_start < rd['t_req'] <= as_of]
    reads_left = [rd for rd in reads_span if rd['left']]
    shown = sorted(k for k in blocks if k + timedelta(days=1) > span_start and k < as_of)
    coverage = {
        'jobs': len(in_span),
        'exam_times': {'known': sum(1 for j in left if j['exam_known']), 'of': len(left)},
        'report_times': {'known': sum(1 for j in left if j['report_known']), 'of': len(left)},
        'pacs_start': {'known': sum(1 for j in left if j['pacs_start']), 'of': len(left)},
        'inconsistent': sum(1 for j in in_span if j['inconsistent']),
        'merged': sum(1 for j in in_span if j['merged']),
        # the reads requested in the span, and those of them with a cached report time
        'reads': len(reads_span),
        'read_times': {'known': sum(1 for rd in reads_left if rd['t_rep']), 'of': len(reads_left)},
        # per duty block (counts only, never a name): the on-call team's UPU
        # exams, the senior's share, how many radiologists are on call
        'on_call': [{'block': k.strftime('%Y-%m-%dT%H:%M'), 'known': blocks[k]['known'],
                     'team_exams': blocks[k]['team'], 'senior_exams': blocks[k]['senior'],
                     'radiologists': blocks[k]['radiologists']} for k in shown],
        'upu_arrivals': {'known': sum(1 for j in upu if j['t_arr']), 'of': len(upu)},
        # open past their cap at as_of: left out of the queue
        'stale': {**{stage: sum(1 for j in jobs if j[stage] and j[stage][1] is None
                                and j[stage][0] + j[stage][2] < as_of)
                     for stage in ('exam', 'report')},
                  'read': never_read},
    }

    return {
        'as_of': as_of.strftime('%Y-%m-%dT%H:%M'),
        'span_h': hours,
        'span_start': span_start.strftime('%Y-%m-%dT%H:%M'),
        'window_min': window_min,
        'step_min': step_min,
        'scope': {'modality': SCOPE_MODALITY, 'section': SCOPE_SECTION, 'work': sorted(SCOPE_LABS)},
        'current': current,
        'series': series,
        'shifts': [shift_summary(k, blocks[k], series, span_start, as_of, step_min) for k in shown],
        'coverage': coverage,
        'truncated': truncated,
        'strain_refs': {'queue': round(refs.queue, 2), 'wait_min': round(refs.wait, 1),
                        'read_queue': round(refs.read_queue, 2), 'read_oldest_min': round(refs.read_oldest, 1)},
        'open_caps_h': {f"{stage}:{m or 'all'}": round(_hours(cap), 2) for (stage, m), cap in caps.items()},
    }


def _waiting(iv, t: datetime) -> bool:
    start, end, cap = _parts(iv)
    return start <= t < (end if end is not None else start + cap)


def shift_summary(start: datetime, blk: dict, series: List[dict], span_start: datetime,
                  as_of: datetime, step_min: int) -> dict:
    """One on-call shift (the on-call hours of the duty block at `start`) in
    a few numbers, to compare shifts: the peak and mean strain, the hours at
    SHIFT_HIGH or more, the team's reports by modality (us = UPU ultrasound
    exams; `ward` = how many of the reads came from a ward) and the team's
    size. `complete`: the whole shift lies in the span analysed. Counts only."""
    frm, end = on_call_from(start), start + timedelta(days=1)
    lo, hi = frm.strftime('%Y-%m-%dT%H:%M'), end.strftime('%Y-%m-%dT%H:%M')
    vals = [p['strain'] for p in series if lo < p['t'] <= hi]
    return {
        'block': start.strftime('%Y-%m-%dT%H:%M'),
        'from': lo, 'to': hi,
        'complete': frm >= span_start and end <= as_of,
        'peak': max(vals) if vals else None,
        'mean': int(round(sum(vals) / len(vals))) if vals else None,
        'hours_high': round(sum(1 for v in vals if v >= SHIFT_HIGH) * step_min / 60.0, 1),
        'reports': dict(blk['reports']),
        'ward': blk['ward'],
        'radiologists': blk['radiologists'],
        'known': blk['known'],
    }
