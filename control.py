"""
Possible planned control: is a UPU (ER) request likely a control the child was
asked to come back for, rather than an emergency?

A score from what is known when the request is made (no outcome), validated
retrospectively on September-October 2026 with tools/upu_called.py: at the
threshold below, about 1.5 UPU ultrasounds a day are flagged and about 78% of
them end non-urgent (home, untreated, no ambulance), against 47% of all. It is a
hint for the radiologist to ask who sent the child, never a verdict, and it
names nobody.

Points:
  +2  discharged from a surgery or orthopaedics ward in the 30 days before
  +2  another UPU visit in the 7 days before
  +2  the surgeon of the child's last surgical stay (90 days) is on call today
      (+3 at weekends, Saturday 08:00 to Monday 08:00)
  +1  discharged from any ward in the 90 days before
  +1  weekday 08:00-14:00
  +1  request within 15 minutes of arrival
  -2  brought by ambulance

The on-call roster is optional: CSV files (date,weekday,line1,line2,... of
surnames, an optional initial, "Popescu O"), listed in hippobridge.cfg
[control] roster as paths or globs, read on each call (they are small and
change monthly). Pure functions apart from load_roster(); tests in
tests/control.py.
"""
import csv
import glob
import re
import unicodedata
from datetime import date, datetime, time, timedelta

THRESHOLD = 4
TITLES = {"dr", "prof", "conf", "sl", "as", "med", "univ", "acad"}


def fold(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


def norm_name(s):
    """A physician's name as comparable tokens (folded, titles dropped)."""
    return [w for w in re.findall(r"[a-z]+", fold(s)) if w not in TITLES]


def ward(s):
    return re.sub(r"\s*\(.*?\)", "", fold(s)).strip()


def parse_time(v):
    """A naive datetime from 'dd/mm/yyyy hh:mm', 'dd.mm.yyyy hh:mm' or ISO."""
    if not v or not isinstance(v, str):
        return None
    v = v.strip()
    for f in ("%d/%m/%Y %H:%M", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(v[:16], f)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(v.replace("Z", "")).replace(tzinfo=None)
    except ValueError:
        return None


def shift_date(t):
    """The roster date a moment belongs to: an on-call day runs 08:00 -> 08:00."""
    return (t - timedelta(hours=8)).date()


def load_roster(patterns):
    """{date: [(surname, initial or '')]} from the roster CSV files."""
    roster = {}
    for pattern in [p.strip() for p in (patterns or "").split(",") if p.strip()]:
        for path in sorted(glob.glob(pattern)):
            with open(path, encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    try:
                        d = date.fromisoformat((row.get("date") or "").strip())
                    except ValueError:
                        continue
                    for col, cell in row.items():
                        if not col or not col.startswith("line") or col.endswith("_cut"):
                            continue
                        parts = norm_name(cell)
                        if not parts:
                            continue
                        sur = max(parts, key=len)
                        ini = next((x for x in parts if x != sur and len(x) == 1), "")
                        roster.setdefault(d, []).append((sur, ini))
    return roster


def on_call(names, roster, d):
    """Whether any of `names` (raw physician names) is on the roster for d."""
    duty = roster.get(d) or []
    for raw in names:
        toks = norm_name(raw)
        for sur, ini in duty:
            if sur in toks and (not ini or any(t.startswith(ini) for t in toks if t != sur)):
                return True
    return False


def presentation_for(req_time, history):
    """(presentation id, start) of the UPU visit a request belongs to: the newest
    presentation that began no later than the request and less than 48 h before."""
    starts = sorted(((parse_time(h.get("start")), str(h.get("presentation_id") or ""))
                     for h in history or [] if h.get("kind") == "presentation"),
                    key=lambda x: x[0] or datetime.min, reverse=True)
    for t, prid in starts:
        if t and prid and t <= req_time:
            return (prid, t) if req_time - t <= timedelta(hours=48) else (None, None)
    return None, None


def assess(req_time, history, transport="", roster=None, holidays=frozenset()):
    """{score, flag, reasons} for one request. `history` is /api/patient's
    history list; `transport` the visit's transport type."""
    reasons, score = [], 0
    prid, arrival = presentation_for(req_time, history)
    arrival = arrival or req_time
    last_end, last_ward, last_medics = None, "", []
    upu7 = None
    for h in history or []:
        st, en = parse_time(h.get("start")), parse_time(h.get("end"))
        kind = h.get("kind")
        if kind == "presentation":
            if st and st < arrival and str(h.get("presentation_id") or "") != prid:
                days = (arrival - st).days
                if days <= 7 and (upu7 is None or days < upu7):
                    upu7 = days
        elif kind in ("admission", "day_admission") and en and en <= arrival:
            if last_end is None or en > last_end:
                last_end = en
                last_ward = ward(h.get("section_out") or h.get("section_in"))
                last_medics = [h.get("medic_out") or "", h.get("medic_in") or ""]
    if last_end is not None:
        days = (arrival - last_end).days
        surgical = "chirurg" in last_ward or "ortoped" in last_ward
        if surgical and days <= 30:
            score += 2
            reasons.append({"code": "surgical_discharge", "days": days})
        if days <= 90:
            score += 1
            if not (surgical and days <= 30):
                reasons.append({"code": "recent_discharge", "days": days})
            duty = shift_date(arrival)
            if surgical and roster and on_call(last_medics, roster, duty):
                # At weekends the treating surgeon's own shift is the clearest
                # sign (10 returns against 2.8 by chance, Sep-Oct 2026).
                score += 3 if duty.weekday() >= 5 else 2
                reasons.append({"code": "surgeon_on_call"})
    if upu7 is not None:
        score += 2
        reasons.append({"code": "recent_upu_visit", "days": upu7})
    weekday = arrival.weekday() < 5 and arrival.date() not in holidays
    if weekday and time(8) <= arrival.time() < time(14):
        score += 1
        reasons.append({"code": "weekday_morning"})
    if prid and timedelta(0) <= req_time - arrival <= timedelta(minutes=15):
        score += 1
        reasons.append({"code": "fast_request"})
    t = fold(transport)
    if "saj" in t or "smurd" in t or "ambulan" in t:
        score -= 2
        reasons.append({"code": "ambulance"})
    return {"score": score, "flag": score >= THRESHOLD, "reasons": reasons}
