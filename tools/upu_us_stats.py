#!/usr/bin/env python3
"""
Monthly statistics of ultrasound requests made by UPU (emergency department).

Two stages, both read-only against the running server:

  fetch    list the US requests (lab 28) day by day from /api/schedule, keep the
           UPU ones, fetch each one's report from /api/study/{id}?justification=0
           for the signing time, and write <out>/requests.csv (anonymised).
  analyze  read requests.csv and write <out>/stats.json (every number) and
           <out>/report.md (the paper): volume, distribution over the day and
           the week, request -> performed -> signed intervals, the on-call
           focus (weekdays 14:00 -> 08:00, weekends and holidays 08:00 -> 08:00)
           and the tests behind the claims.

Privacy: the CSV holds a salted hash of the request id, timestamps, status,
priority and a salted hash of the signer. No patient name, CNP, barcode or
report text is ever kept; <out>/cache.jsonl (the resume cache) holds the raw
request ids, timestamps and signer names, so keep <out> on this machine.

Credentials: --username/--password, else HYP_USER / HYP_PASS, else
[worklist] username/password from worklist.cfg.

Example:
  tools/upu_us_stats.py all --since 2026-10-01 --until 2026-10-26 --out _testing_/upu-2026-10
"""
import argparse
import asyncio
import configparser
import csv
import hashlib
import json
import math
import os
import random
import secrets
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from datetime import time as dtime

BASE_URL = os.getenv("HIPPOBRIDGE_URL", "http://127.0.0.1:44660")
US_LAB = "28"
LIMIT = 200
PENDING_HOURS = 12              # a request younger than this may still be waiting
MAX_MINUTES = 7 * 24 * 60       # an interval longer than this is a data error
CANCELLED = {"revoked", "entered-in-error"}
CLASSES = ("day", "weeknight", "weekend")
CLASS_LABEL = {"day": "weekday 08-14", "weeknight": "weekday 14-08",
               "weekend": "weekend/holiday 08-08"}
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
CSV_FIELDS = ("rid", "requested", "performed", "signed", "status", "priority",
              "payment", "validator", "n_studies", "n_validated",
              "v_arrival", "v_triage_time", "v_triage", "v_decision", "v_admission")
VISIT_KEYS = ("v_done", "v_arrival", "v_triage_time", "v_triage", "v_decision", "v_admission")


# ---------------------------------------------------------------- time helpers

def parse_dt(v):
    """A naive datetime from the server's formats, or None."""
    if not v or not isinstance(v, str):
        return None
    v = v.strip()
    try:
        return datetime.fromisoformat(v.replace("Z", "")).replace(tzinfo=None)
    except ValueError:
        pass
    for f in ("%d/%m/%Y %H:%M", "%d %b %Y %H:%M", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(v, f)
        except ValueError:
            pass
    return None


def shift_of(t, holidays=frozenset()):
    """(class, shift date) of a moment.

    A shift day runs 08:00 -> 08:00 and is named by the date it starts on.
    On a Saturday, Sunday or holiday it is one 24 h on-call shift ("weekend");
    on a working day 08:00-14:00 is routine ("day") and 14:00 -> 08:00 is the
    on-call night ("weeknight").
    """
    d = (t - timedelta(hours=8)).date()
    if d.weekday() >= 5 or d in holidays:
        return "weekend", d
    if t >= datetime.combine(d, dtime(14)):
        return "weeknight", d
    return "day", d


def shift_bounds(cls, d):
    start = datetime.combine(d, dtime(14 if cls == "weeknight" else 8))
    return start, datetime.combine(d + timedelta(days=1), dtime(8))


def minutes(a, b):
    return None if a is None or b is None else (b - a).total_seconds() / 60


# --------------------------------------------------------------------- statistics

def percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def summarize(vals):
    s = sorted(vals)
    if not s:
        return {"n": 0}
    return {"n": len(s), "mean": sum(s) / len(s), "min": s[0],
            "p25": percentile(s, 25), "median": percentile(s, 50),
            "p75": percentile(s, 75), "p90": percentile(s, 90),
            "p95": percentile(s, 95), "max": s[-1]}


def median_ci(vals, reps=2000, seed=12345):
    """Percentile bootstrap 95 % interval of the median (seeded, repeatable)."""
    if len(vals) < 5:
        return None
    rnd = random.Random(seed)
    n = len(vals)
    meds = sorted(percentile(sorted(rnd.choices(vals, k=n)), 50) for _ in range(reps))
    return percentile(meds, 2.5), percentile(meds, 97.5)


def midranks(vals):
    order = sorted(range(len(vals)), key=vals.__getitem__)
    ranks, i = [0.0] * len(vals), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def mann_whitney(a, b):
    """Two-sided Mann-Whitney U, normal approximation with tie correction.

    Returns n1, n2, U, z, p and the probability that a value of `a` exceeds
    one of `b` (ties half), which is the effect size.
    """
    n1, n2 = len(a), len(b)
    if n1 < 3 or n2 < 3:
        return None
    ranks = midranks(list(a) + list(b))
    u1 = sum(ranks[:n1]) - n1 * (n1 + 1) / 2
    n = n1 + n2
    ties = sum(c ** 3 - c for c in Counter(list(a) + list(b)).values())
    var = n1 * n2 / 12 * ((n + 1) - ties / (n * (n - 1)))
    if var <= 0:
        return None
    z = (u1 - n1 * n2 / 2) / math.sqrt(var)
    return {"n1": n1, "n2": n2, "U": u1, "z": z,
            "p": math.erfc(abs(z) / math.sqrt(2)), "prob_a_gt_b": u1 / (n1 * n2)}


def spearman(x, y):
    n = len(x)
    if n < 4:
        return None
    rx, ry = midranks(x), midranks(y)
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    rho = sxy / math.sqrt(sxx * syy)
    z = rho * math.sqrt(n - 1)          # large-sample approximation
    return {"n": n, "rho": rho, "p": math.erfc(abs(z) / math.sqrt(2))}


def dispersion(counts):
    """Variance-to-mean ratio of counts: 1 for Poisson, above 1 = clumped."""
    n = len(counts)
    if n < 2:
        return None
    m = sum(counts) / n
    if m == 0:
        return None
    var = sum((c - m) ** 2 for c in counts) / (n - 1)
    return {"n": n, "mean": m, "sd": math.sqrt(var), "index": var / m,
            "min": min(counts), "max": max(counts)}


# --------------------------------------------------------------------- fetching

def log(msg):
    print(f"{datetime.now():%H:%M:%S} {msg}", flush=True)


def worklist_creds():
    cfg = configparser.ConfigParser()
    cfg.read(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "worklist.cfg"))
    return (cfg.get("worklist", "username", fallback=None),
            cfg.get("worklist", "password", fallback=None))


class Gentle:
    """Sequential GETs with a fixed pause and backoff retry on failure."""

    def __init__(self, session, base):
        import aiohttp
        self.aiohttp, self.s, self.base, self.errors = aiohttp, session, base, 0

    async def get(self, path, params, pause):
        for attempt in range(4):
            await asyncio.sleep(pause if attempt == 0 else 10 * 2 ** attempt)
            try:
                async with self.s.get(self.base + path, params=params) as r:
                    if r.status == 401:
                        sys.exit("401 Unauthorized: check HYP_USER/HYP_PASS")
                    if r.status < 500:
                        data = await r.json()
                        self.errors = 0
                        return data
                    log(f"  HTTP {r.status} on {path}")
            except (self.aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
                log(f"  {type(e).__name__} on {path}")
        self.errors += 1
        if self.errors >= 5:
            sys.exit("Too many consecutive failures, aborting (re-run with --resume)")
        return None


def is_ward(row, ward):
    return (row.get("section") or "").strip().upper() == ward.upper()


async def list_day(g, d, ward, lab, refresh, pause):
    """(rows of the ward, every section seen) for one request day."""
    params = {"start_date": d.isoformat(), "end_date": d.isoformat(),
              "lab_id": lab, "limit": LIMIT}
    if refresh:
        params["refresh"] = "1"
    data = await g.get("/api/schedule", params, pause)
    if data is None:
        return None, Counter()
    rows = data.get("requests") or []
    sections = Counter((r.get("section") or "?").strip().upper() for r in rows)
    if len(rows) >= LIMIT:
        # The cap may have cut the day: ask the server for the ward alone.
        log(f"  {d}: {len(rows)} rows hit the {LIMIT} cap, asking for the ward alone")
        more = await g.get("/api/schedule", {**params, "section_name": ward}, pause)
        if more is not None:
            rows = more.get("requests") or []
            if len(rows) >= LIMIT:
                log(f"  WARNING {d}: the ward alone still hits the cap, truncated")
    return [r for r in rows if is_ward(r, ward)], sections


def new_record(row):
    return {"id": str(row.get("request_id") or ""),
            "requested": row.get("date_time") or "",
            "performed": row.get("performed_at") or "",
            "status": row.get("status") or "",
            "priority": row.get("priority") or "",
            "payment": row.get("payment_type") or "",
            "signed": "", "validator": "", "n_studies": 0, "n_validated": 0,
            "studied": False}


def apply_study(rec, res):
    """Signing time and signer from an /api/study answer; false if it failed."""
    if not res or res.get("status") != "success":
        return False
    studies = res.get("studies") or []
    done = [(parse_dt(s.get("validation_date")), (s.get("validator") or "").strip())
            for s in studies]
    done = [x for x in done if x[0] is not None]
    rec["n_studies"], rec["n_validated"], rec["studied"] = len(studies), len(done), True
    if done:
        last = max(done, key=lambda x: x[0])
        rec["signed"], rec["validator"] = last[0].strftime("%Y-%m-%d %H:%M"), last[1]
    else:
        rec["signed"] = rec["validator"] = ""
    return True


def load_cache(path):
    cache = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                cache[rec["id"]] = rec
    return cache


def save_cache(path, cache):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for rec in cache.values():
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def needs_study(rec, resume):
    if rec["status"] in CANCELLED:
        return False
    if not rec["studied"]:
        return True
    return not resume and (rec["n_studies"] == 0 or rec["n_validated"] < rec["n_studies"])


def salt_for(out):
    path = os.path.join(out, ".salt")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(16))
        os.chmod(path, 0o600)
    with open(path) as f:
        return f.read().strip()


def digest(salt, kind, value, n):
    return hashlib.sha256(f"{salt}:{kind}:{value}".encode()).hexdigest()[:n]


def export_csv(out, cache):
    salt = salt_for(out)
    path = os.path.join(out, "requests.csv")
    recs = sorted(cache.values(), key=lambda r: (r["requested"], r["id"]))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, CSV_FIELDS)
        w.writeheader()
        for r in recs:
            w.writerow({"rid": digest(salt, "req", r["id"], 10),
                        **{k: r[k] for k in ("requested", "performed", "signed",
                                             "status", "priority", "payment",
                                             "n_studies", "n_validated")},
                        **{k: r.get(k) or "" for k in CSV_FIELDS if k.startswith("v_")},
                        "validator": digest(salt, "val", r["validator"], 6)
                        if r["validator"] else ""})
    return path, len(recs)


async def fetch(args):
    import aiohttp
    os.makedirs(args.out, exist_ok=True)
    cache_path = os.path.join(args.out, "cache.jsonl")
    cache = load_cache(cache_path)
    since, until = date.fromisoformat(args.since), date.fromisoformat(args.until)
    log(f"Fetching {args.ward} US requests {since} .. {until} "
        f"({(until - since).days + 1} days) from {args.url}; {len(cache)} cached")
    sections, t0 = Counter(), time.monotonic()
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(args.username, args.password),
            timeout=timeout) as session:
        g = Gentle(session, args.url)
        d = since
        while d <= until:
            fresh = args.refresh or d >= date.today() - timedelta(days=1)
            rows, secs = await list_day(g, d, args.ward, US_LAB, fresh,
                                        args.pause_schedule)
            if rows is None:
                log(f"{d}: listing FAILED, skipped (re-run to retry)")
                d += timedelta(days=1)
                continue
            sections.update(secs)
            for row in rows:
                rid = str(row.get("request_id") or "")
                if not rid:
                    continue
                rec = new_record(row)
                old = cache.get(rid)
                if old:        # the listing is current, the study part is kept
                    for k in ("signed", "validator", "n_studies", "n_validated", "studied") + VISIT_KEYS:
                        if k in old:
                            rec[k] = old[k]
                cache[rid] = rec
            todo = [cache[str(r.get("request_id"))] for r in rows
                    if r.get("request_id") and needs_study(
                        cache[str(r["request_id"])], args.resume)]
            failed = 0
            for n, rec in enumerate(todo, 1):
                res = await g.get(f"/api/study/{rec['id']}",
                                  {"justification": "0"}, args.pause_study)
                if not apply_study(rec, res):
                    failed += 1
                if n % 25 == 0 and n < len(todo):
                    log(f"    {d}: studies {n}/{len(todo)}")
            save_cache(cache_path, cache)
            signed = sum(1 for r in rows if cache[str(r["request_id"])]["signed"])
            log(f"{d}: {len(rows)} {args.ward} requests, {signed} signed, "
                f"{len(todo)} studies read, {failed} failed")
            d += timedelta(days=1)
    with open(os.path.join(args.out, "meta.json"), "w") as f:
        json.dump({"since": args.since, "until": args.until, "ward": args.ward,
                   "sections_seen": dict(sections.most_common()),
                   "fetched_at": datetime.now().isoformat(timespec="seconds")}, f, indent=1)
    path, n = export_csv(args.out, cache)
    log(f"Wrote {n} rows to {path} in {timedelta(seconds=int(time.monotonic() - t0))}")
    log("Sections seen (all wards, for checking the UPU filter): "
        + ", ".join(f"{k}={v}" for k, v in sections.most_common(12)))


def pres_time(v):
    """A presentation page's 'dd/mm/yyyy hh:mm' as a naive datetime, or None
    (the triage time is sometimes a bare date: then it is no time)."""
    if not v or not isinstance(v, str) or ":" not in v:
        return None
    try:
        return datetime.strptime(v.strip()[:16], "%d/%m/%Y %H:%M")
    except ValueError:
        return None


def iso(t):
    return t.strftime("%Y-%m-%d %H:%M") if t else ""


def decision_kind(text):
    """Disposition text of the presentation -> a short class."""
    t = (text or "").lower()
    if "fara aviz" in t or "fără aviz" in t:
        return "left_unadvised"
    if "domiciliu" in t:
        return "home"
    if "intern" in t:
        return "admitted"
    if "transfer" in t or "unitate" in t:
        return "transfer"
    if "refuz" in t:
        return "refused"
    return "other" if t.strip() else "unknown"


def match_presentation(req_time, presentations):
    """The presentation a request belongs to: the newest one that began no
    later than the request, if it began less than 48 h before it.

    `presentations` is [(arrival datetime, payload)], newest first."""
    for arrival, payload in presentations:
        if arrival is None or arrival > req_time:
            continue
        if req_time - arrival <= timedelta(hours=48):
            return arrival, payload
        return None
    return None


def apply_visit(rec, arrival, payload):
    pr = payload.get("presentation") or {}
    adm = payload.get("admission") or {}
    rec.update(v_done=True, v_arrival=iso(arrival),
               v_triage_time=iso(pres_time(pr.get("triage_time"))),
               v_triage=pr.get("triage") or "", v_decision=pr.get("decision") or "",
               v_admission=iso(pres_time(adm.get("date_time"))))


async def fetch_visits(args):
    """For each cached request, the UPU visit it belongs to: arrival, triage,
    disposition and admission time. Nothing identifying is kept."""
    import aiohttp
    cache_path = os.path.join(args.out, "cache.jsonl")
    cache = load_cache(cache_path)
    todo = [r for r in cache.values() if not r.get("v_done") and not r.get("v_failed")]
    todo.sort(key=lambda r: r["requested"])
    log(f"Visits: {len(todo)} of {len(cache)} requests to look up")
    patients, presentations = {}, {}      # in memory only
    timeout = aiohttp.ClientTimeout(total=120)
    t0, found, none = time.monotonic(), 0, 0
    async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(args.username, args.password),
                                     timeout=timeout) as session:
        g = Gentle(session, args.url)
        for n, rec in enumerate(todo, 1):
            req_time = parse_dt(rec["requested"])
            rq = await g.get(f"/api/request/{rec['id']}", {}, args.pause_visit)
            pid = ((rq or {}).get("patient") or {}).get("id")
            if rq is None:
                continue                  # try again on the next run
            if not pid:
                rec["v_done"] = True
                none += 1
                continue
            if pid not in patients:
                pat = await g.get(f"/api/patient/{pid}", {}, args.pause_visit)
                if pat is None:
                    continue
                ids = pat.get("presentation") or []
                ids = ids if isinstance(ids, list) else [ids]
                patients[pid] = sorted((i for i in ids if str(i).isdigit()), key=int, reverse=True)
            chain, ok = [], True
            for prid in patients[pid][:4]:
                if prid not in presentations:
                    d = await g.get(f"/api/presentation/{prid}", {}, args.pause_visit)
                    if d is None:
                        ok = False
                        break
                    presentations[prid] = (pres_time((d.get("presentation") or {}).get("date_time")), d)
                chain.append(presentations[prid])
                if chain[-1][0] is not None and chain[-1][0] <= req_time:
                    break
            if not ok:
                continue
            hit = match_presentation(req_time, chain)
            rec["v_done"] = True
            if hit:
                apply_visit(rec, *hit)
                found += 1
            else:
                none += 1
            if n % 50 == 0:
                save_cache(cache_path, cache)
                log(f"    visits {n}/{len(todo)} (found {found}, none {none})")
    save_cache(cache_path, cache)
    path, rows = export_csv(args.out, cache)
    log(f"Visits done in {timedelta(seconds=int(time.monotonic() - t0))}: found {found}, "
        f"no matching presentation {none}; wrote {rows} rows to {path}")


# --------------------------------------------------------------------- analysis

def load_requests(out, holidays):
    recs = []
    with open(os.path.join(out, "requests.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = parse_dt(r["requested"])
            if t is None:
                continue
            r["t_req"], r["t_perf"], r["t_sign"] = t, parse_dt(r["performed"]), parse_dt(r["signed"])
            r["cancelled"] = r["status"] in CANCELLED
            r["cls"], r["shift"] = shift_of(t, holidays)
            r["i_rp"] = minutes(t, r["t_perf"])
            r["i_ps"] = minutes(r["t_perf"], r["t_sign"])
            r["i_rs"] = minutes(t, r["t_sign"])
            r["t_arr"], r["t_tri"], r["t_adm"] = (parse_dt(r.get("v_arrival")),
                                                  parse_dt(r.get("v_triage_time")),
                                                  parse_dt(r.get("v_admission")))
            r["kind"] = decision_kind(r.get("v_decision")) if r["t_arr"] else None
            r["i_ar"] = minutes(r["t_arr"], t)            # arrival -> request
            r["i_tr"] = minutes(r["t_tri"], t)            # triage -> request
            r["i_as"] = minutes(r["t_arr"], r["t_sign"])  # arrival -> signed
            r["i_sa"] = minutes(r["t_sign"], r["t_adm"])  # signed -> ward admission
            r["i_aa"] = minutes(r["t_arr"], r["t_adm"])   # arrival -> ward admission
            recs.append(r)
    return recs


def clean(vals):
    """(valid values, count of negative, count over MAX_MINUTES) of intervals."""
    ok = [v for v in vals if v is not None and 0 <= v <= MAX_MINUTES]
    neg = sum(1 for v in vals if v is not None and v < 0)
    big = sum(1 for v in vals if v is not None and v > MAX_MINUTES)
    return ok, neg, big


METRICS = (("i_rp", "request -> performed"), ("i_ps", "performed -> signed"),
           ("i_rs", "request -> signed"))


def interval_stats(recs, key, ci=False):
    vals = [r[key] for r in recs]
    ok, neg, big = clean(vals)
    s = summarize(ok)
    s.update(total=len(recs), missing=sum(1 for v in vals if v is None),
             negative=neg, too_long=big)
    if ci and ok:
        s["median_ci"] = median_ci(ok)
    return s


def within(recs, key, limit):
    ok, _, _ = clean([r[key] for r in recs])
    return {"n": len(ok), "share": sum(1 for v in ok if v <= limit) / len(ok)} if ok else None


def outcome(r, as_of):
    """What became of a request: signed, unsigned (done, report missing),
    cancelled, pending (too recent to judge) or left (never performed)."""
    if r["t_sign"]:
        return "signed"
    if r["cancelled"]:
        return "cancelled"
    if r["t_perf"]:
        return "performed_unsigned"
    if (as_of - r["t_req"]).total_seconds() < PENDING_HOURS * 3600:
        return "pending"
    return "left"


def two_proportions(x1, n1, x2, n2):
    """Two-sided z test of two shares; None when a group is empty."""
    if not n1 or not n2:
        return None
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return None
    z = (x1 / n1 - x2 / n2) / se
    return {"x1": x1, "n1": n1, "x2": x2, "n2": n2, "z": z,
            "p": math.erfc(abs(z) / math.sqrt(2))}


def outcome_stats(recs, as_of):
    """Requests that never became a signed report, i.e. mostly patients who
    left (cancelled, or never performed) before the exam."""
    for r in recs:
        r["outcome"] = outcome(r, as_of)
    judged = [r for r in recs if r["outcome"] != "pending"]
    never = lambda rs: sum(1 for r in rs if r["outcome"] in ("cancelled", "left"))  # noqa: E731
    o = {"as_of": as_of.isoformat(timespec="minutes"),
         "counts": dict(Counter(r["outcome"] for r in recs)),
         "judged": len(judged), "left": never(judged)}
    o["rate"] = o["left"] / len(judged) if judged else None
    o["unsigned_rate"] = (sum(1 for r in judged if r["outcome"] != "signed") / len(judged)
                          if judged else None)
    o["by_class"] = {c: {"n": len(sub), "left": never(sub)}
                     for c in CLASSES for sub in [[r for r in judged if r["cls"] == c]]}
    o["by_weekday"] = [{"n": len(sub), "left": never(sub)} for w in range(7)
                       for sub in [[r for r in judged if r["t_req"].weekday() == w]]]
    o["by_hour"] = [{"n": len(sub), "left": never(sub)} for h in range(24)
                    for sub in [[r for r in judged if r["t_req"].hour == h]]]
    oncall = [r for r in judged if r["cls"] != "day"]
    day = [r for r in judged if r["cls"] == "day"]
    o["test_oncall_vs_day"] = two_proportions(never(oncall), len(oncall), never(day), len(day))
    wn = [r for r in judged if r["cls"] == "weeknight"]
    we = [r for r in judged if r["cls"] == "weekend"]
    o["test_weekend_vs_weeknight"] = two_proportions(never(we), len(we), never(wn), len(wn))
    # does the share who left follow the wait of those who were served?
    served = [r for r in recs if r["outcome"] in ("signed", "performed_unsigned")]
    hs = [h for h in range(24) if o["by_hour"][h]["n"] >= 5 and
          len(clean([r["i_rp"] for r in served if r["t_req"].hour == h])[0]) >= 3]
    rate = [o["by_hour"][h]["left"] / o["by_hour"][h]["n"] for h in hs]
    o["hour_left_vs_wait"] = spearman(
        rate, [percentile(sorted(clean([r["i_rp"] for r in served if r["t_req"].hour == h])[0]), 50)
               for h in hs])
    o["hour_left_vs_volume"] = spearman(rate, [o["by_hour"][h]["n"] for h in hs])
    # is the wait of those served longer on days when someone left?
    day_left = Counter(r["t_req"].date() for r in recs if r["outcome"] in ("cancelled", "left"))
    with_left = [r["i_rp"] for r in served if day_left.get(r["t_req"].date()) and r["i_rp"] is not None]
    without = [r["i_rp"] for r in served if not day_left.get(r["t_req"].date()) and r["i_rp"] is not None]
    o["wait_days_with_vs_without_left"] = mann_whitney(clean(with_left)[0], clean(without)[0])
    return o


VISIT_METRICS = (("i_ar", "arrival -> request"),
                 ("i_rs", "request -> signed"), ("i_as", "arrival -> signed"))


def visit_stats(recs):
    """The UPU visit around each request: where the ultrasound sits in the stay."""
    vis = [r for r in recs if r["t_arr"]]
    v = {"matched": len(vis), "total": len(recs)}
    if not vis:
        return v
    v["kinds"] = dict(Counter(r["kind"] for r in vis))
    v["decisions"] = dict(Counter(r.get("v_decision") or "?" for r in vis).most_common(12))
    v["triage"] = dict(Counter(r.get("v_triage") or "?" for r in vis))
    v["intervals"] = {"all": {k: interval_stats(vis, k, ci=True) for k, _ in VISIT_METRICS}}
    for c in CLASSES:
        sub = [r for r in vis if r["cls"] == c]
        v["intervals"][c] = {k: interval_stats(sub, k) for k, _ in VISIT_METRICS}
    for lvl in sorted({r.get("v_triage") or "?" for r in vis}):
        sub = [r for r in vis if (r.get("v_triage") or "?") == lvl]
        v["intervals"]["triage:" + lvl] = {k: interval_stats(sub, k) for k, _ in VISIT_METRICS}
    v["share_before_request"] = {
        lim: within(vis, "i_ar", lim) for lim in (15, 30, 60, 120)}

    # patients admitted to a ward: the whole stay is timed
    adm = [r for r in vis if r["kind"] == "admitted"]
    seg = [(r["i_ar"], r["i_rs"], r["i_sa"], r["i_aa"]) for r in adm
           if None not in (r["i_ar"], r["i_rs"], r["i_sa"], r["i_aa"])
           and r["i_ar"] >= 0 and r["i_rs"] >= 0 and r["i_sa"] >= 0 and r["i_aa"] > 0]
    v["admitted"] = {
        "n": len(adm), "with_admission_time": sum(1 for r in adm if r["t_adm"]),
        "i_aa": interval_stats(adm, "i_aa", ci=True), "i_sa": interval_stats(adm, "i_sa", ci=True),
        "signed_after_admission": sum(1 for r in adm if r["i_sa"] is not None and r["i_sa"] < 0),
        "complete": len(seg)}
    if seg:
        share = lambda i: sorted(x[i] / x[3] for x in seg)  # noqa: E731
        v["admitted"]["shares"] = {name: percentile(share(i), 50) for name, i in
                                   (("before_request", 0), ("request_to_signed", 1), ("signed_to_admission", 2))}
        v["admitted"]["us_dominates"] = sum(1 for x in seg if x[1] > max(x[0], x[2])) / len(seg)

    # patients who left without notice
    left = [r for r in vis if r["kind"] == "left_unadvised"]
    rest = [r for r in vis if r["kind"] != "left_unadvised"]
    home = [r for r in vis if r["kind"] == "home"]
    lu = {"n": len(left), "rate": len(left) / len(vis),
          "outcomes": dict(Counter(r["outcome"] for r in left)),
          "by_class": {c: {"n": len([r for r in vis if r["cls"] == c]),
                           "left": len([r for r in left if r["cls"] == c])} for c in CLASSES},
          "by_hour": [{"n": len([r for r in vis if r["t_req"].hour == h]),
                       "left": len([r for r in left if r["t_req"].hour == h])} for h in range(24)]}
    lu["intervals"] = {k: interval_stats(left, k) for k, _ in VISIT_METRICS}
    lu["intervals"]["i_rp"] = interval_stats(left, "i_rp")
    lu["tests"] = {}
    for k in ("i_ar", "i_rp", "i_rs", "i_as"):
        a, b = (clean([r[k] for r in left])[0], clean([r[k] for r in home])[0])
        lu["tests"][k] = mann_whitney(a, b)
    d = lu["by_class"]
    on_n = d["weeknight"]["n"] + d["weekend"]["n"]
    on_l = d["weeknight"]["left"] + d["weekend"]["left"]
    lu["test_oncall_vs_day"] = two_proportions(on_l, on_n, d["day"]["left"], d["day"]["n"])
    v["left_unadvised"] = lu
    # how the proxy of section 6 agrees with the recorded disposition
    v["proxy_vs_disposition"] = {
        k: dict(Counter(r["outcome"] for r in vis if r["kind"] == k))
        for k in sorted({r["kind"] for r in vis})}
    # waiting before the request, per disposition
    v["by_kind"] = {k: {m: interval_stats([r for r in vis if r["kind"] == k], m)
                        for m in ("i_ar", "i_rp", "i_rs")}
                    for k in sorted({r["kind"] for r in vis})}
    return v


def analyze_data(recs, since, until, holidays=frozenset(), as_of=None):
    live = [r for r in recs if not r["cancelled"]]
    ra = {"range": [since.isoformat(), until.isoformat()],
          "requests": len(recs), "cancelled": len(recs) - len(live),
          "active": len(recs)}
    if not recs:
        return ra
    days = (until - since).days + 1
    by_day = Counter(r["t_req"].date() for r in recs)
    daily = [by_day.get(since + timedelta(days=i), 0) for i in range(days)]
    ra["daily"] = {(since + timedelta(days=i)).isoformat(): daily[i] for i in range(days)}
    ra["daily_stats"] = dispersion(daily)
    ra["urgent_share"] = sum(1 for r in recs if r["priority"] == "urgent") / len(recs)
    ra["priority"] = dict(Counter(r["priority"] or "?" for r in recs))
    ra["status"] = dict(Counter(r["status"] or "?" for r in recs))

    # volume by class and weekday
    ra["by_class"] = {c: sum(1 for r in recs if r["cls"] == c) for c in CLASSES}
    ra["by_weekday"] = [sum(1 for r in recs if r["t_req"].weekday() == w) for w in range(7)]
    weekday_days = [daily[i] for i in range(days) if (since + timedelta(days=i)).weekday() < 5]
    weekend_days = [daily[i] for i in range(days) if (since + timedelta(days=i)).weekday() >= 5]
    ra["calendar_days"] = {"weekday": dispersion(weekday_days), "weekend": dispersion(weekend_days),
                           "mw_weekend_vs_weekday": mann_whitney(weekend_days, weekday_days)}

    # hours
    hours = [[0] * 24 for _ in range(7)]
    for r in recs:
        hours[r["t_req"].weekday()][r["t_req"].hour] += 1
    ra["weekday_hour"] = hours
    ra["by_hour"] = [sum(hours[w][h] for w in range(7)) for h in range(24)]
    ra["by_hour_oncall"] = [sum(1 for r in recs if r["t_req"].hour == h and r["cls"] != "day")
                            for h in range(24)]
    ra["hour_intervals"] = {}
    for h in range(24):
        sub = [r for r in live if r["t_req"].hour == h]
        ra["hour_intervals"][h] = {k: interval_stats(sub, k)
                                   for k, _ in METRICS if k != "i_ps"}
    sign_hours = Counter(r["t_sign"].hour for r in live if r["t_sign"])
    ra["sign_hour"] = [sign_hours.get(h, 0) for h in range(24)]

    # on-call shifts, only those that lie wholly inside the range
    lo, hi = datetime.combine(since, dtime(0)), datetime.combine(until + timedelta(days=1), dtime(0))
    shifts = defaultdict(list)
    for r in recs:
        if r["cls"] != "day":
            shifts[(r["cls"], r["shift"])].append(r)
    complete, partial = {}, []
    for i in range(-1, days):      # every shift of the period, empty ones too
        d = since + timedelta(days=i)
        c = "weekend" if d.weekday() >= 5 or d in holidays else "weeknight"
        s, e = shift_bounds(c, d)
        if s >= lo and e <= hi:
            complete[(c, d)] = shifts.get((c, d), [])
        elif s < hi and e > lo:
            partial.append(f"{d.isoformat()} {c}")
    ra["shifts"] = {"complete": len(complete), "partial": partial}
    ra["shift_counts"] = {c: dispersion([len(rs) for (cc, _), rs in complete.items() if cc == c])
                          for c in ("weeknight", "weekend")}
    ra["shift_list"] = [{"date": d.isoformat(), "class": c, "n": len(rs)}
                        for (c, d), rs in complete.items()]
    # closing the shift: signed before the 08:00 that ends it
    closing = {}
    for c in ("weeknight", "weekend"):
        rs = [r for r in recs if r["cls"] == c]
        done = [r for r in rs if r["t_sign"] and r["t_sign"] <= shift_bounds(c, r["shift"])[1]]
        closing[c] = {"n": len(rs), "signed_by_end": len(done),
                      "signed_ever": sum(1 for r in rs if r["t_sign"])}
    ra["closing"] = closing

    ra["outcomes"] = outcome_stats(recs, as_of or datetime.now())
    ra["visits"] = visit_stats(recs)

    # intervals
    ra["intervals"] = {"all": {k: interval_stats(live, k, ci=True) for k, _ in METRICS}}
    for c in CLASSES:
        sub = [r for r in live if r["cls"] == c]
        ra["intervals"][c] = {k: interval_stats(sub, k, ci=True) for k, _ in METRICS}
    for p in sorted({r["priority"] or "?" for r in live}):
        sub = [r for r in live if (r["priority"] or "?") == p]
        ra["intervals"]["priority:" + p] = {k: interval_stats(sub, k) for k, _ in METRICS}
    ra["thresholds"] = {}
    for key, _ in METRICS:
        ra["thresholds"][key] = {
            lim: {c: within([r for r in live if c == "all" or r["cls"] == c], key, lim)
                  for c in ("all",) + CLASSES} for lim in (15, 30, 60, 120, 240)}

    # tests
    tests = {}
    for key, _ in METRICS:
        oncall = clean([r[key] for r in live if r["cls"] != "day"])[0]
        day = clean([r[key] for r in live if r["cls"] == "day"])[0]
        tests[f"{key}:oncall_vs_day"] = mann_whitney(oncall, day)
        wn = clean([r[key] for r in live if r["cls"] == "weeknight"])[0]
        we = clean([r[key] for r in live if r["cls"] == "weekend"])[0]
        tests[f"{key}:weekend_vs_weeknight"] = mann_whitney(we, wn)
    ra["tests"] = tests
    corr = {}
    for key in ("i_rp", "i_rs"):
        hs = [h for h in range(24) if ra["hour_intervals"][h][key].get("n", 0) >= 3]
        corr[key] = spearman([ra["by_hour"][h] for h in hs],
                             [ra["hour_intervals"][h][key]["median"] for h in hs])
    ra["hour_volume_vs_delay"] = corr

    # signers, labelled A, B, ... by workload
    cnt = Counter(r["validator"] for r in live if r["validator"])
    labels = {v: chr(65 + i) if i < 26 else f"S{i}" for i, (v, _) in enumerate(cnt.most_common())}
    ra["signers"] = []
    for v, n in cnt.most_common():
        sub = [r for r in live if r["validator"] == v]
        ra["signers"].append({
            "label": labels[v], "n": n,
            "oncall_share": sum(1 for r in sub if r["cls"] != "day") / n,
            "i_ps": interval_stats(sub, "i_ps"), "i_rs": interval_stats(sub, "i_rs")})
    return ra


# ----------------------------------------------------------------------- report

def f1(v):
    return "-" if v is None else f"{v:,.1f}"


def f0(v):
    return "-" if v is None else f"{v:,.0f}"


def pct(v):
    return "-" if v is None else f"{100 * v:.0f}%"


def pval(p):
    return "-" if p is None else ("<0.001" if p < 0.001 else f"{p:.3f}")


def dur(m):
    """Minutes as a short human string."""
    if m is None:
        return "-"
    if m < 90:
        return f"{m:.0f} min"
    if m < 48 * 60:
        return f"{m / 60:.1f} h"
    return f"{m / 1440:.1f} d"


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def bar(v, top, width=30):
    return "█" * (round(width * v / top) if top else 0)


def stat_row(label, s):
    ci = s.get("median_ci")
    med = f"{dur(s.get('median'))}" + (f" ({dur(ci[0])}-{dur(ci[1])})" if ci else "")
    return [label, s.get("n", 0), s.get("missing", 0),
            med if s.get("n") else "-", dur(s.get("mean")), dur(s.get("p75")),
            dur(s.get("p90")), dur(s.get("p95")), dur(s.get("max"))]


STAT_HEAD = ["", "n", "missing", "median (95% CI)", "mean", "p75", "p90", "p95", "max"]


def test_line(name, t, a, b, unit="minutes"):
    if not t:
        return f"- {name}: too few values to test."
    direction = f"{a} higher" if t["prob_a_gt_b"] > 0.5 else f"{b} higher"
    return (f"- {name}: n = {t['n1']} vs {t['n2']}, Mann-Whitney z = {t['z']:.2f}, "
            f"p {('= ' + pval(t['p'])) if t['p'] >= 0.001 else '< 0.001'}; "
            f"P({a} > {b}) = {t['prob_a_gt_b']:.2f} ({direction}"
            f"{', significant' if t['p'] < 0.05 else ', not significant'}).")


def render_left(add, ra):
    o = ra["outcomes"]
    c = o["counts"]
    add("A request that is cancelled, or never performed and never signed, is read here as a patient who "
        "may have left before the exam. It is only a guess: section 7 compares it with the disposition the "
        "visit records, and the two overlap little. Requests younger than "
        f"{PENDING_HOURS} h at {o['as_of']} may still be waiting and are not judged. Performed but not yet "
        "signed reports are a different thing (a missing report) and are counted apart.\n")
    add(table(["outcome", "requests", "share"],
              [[k, c.get(k, 0), pct(c.get(k, 0) / ra["active"])]
               for k in ("signed", "performed_unsigned", "cancelled", "left", "pending")]))
    if not o["judged"]:
        return
    add(f"\nLeft before the exam: **{o['left']} of {o['judged']} judged requests ({pct(o['rate'])})**; "
        f"no signed report for any reason: {pct(o['unsigned_rate'])}.\n")
    add("### By shift class\n")
    add(table(["shift class", "judged", "left", "rate"],
              [[CLASS_LABEL[k], v["n"], v["left"], pct(v["left"] / v["n"]) if v["n"] else "-"]
               for k, v in o["by_class"].items()]))
    add("")
    for name, t in (("on-call vs routine hours", o["test_oncall_vs_day"]),
                    ("weekend vs weekday night", o["test_weekend_vs_weeknight"])):
        if t:
            add(f"- {name}: {pct(t['x1'] / t['n1'])} ({t['x1']}/{t['n1']}) vs {pct(t['x2'] / t['n2'])} "
                f"({t['x2']}/{t['n2']}), two-proportion z = {t['z']:.2f}, p {pval(t['p'])}"
                + (", significant." if t["p"] < 0.05 else ", not significant."))
    add("\n### By weekday\n")
    add(table(["day", "judged", "left", "rate"],
              [[WEEKDAYS[w], v["n"], v["left"], pct(v["left"] / v["n"]) if v["n"] else "-"]
               for w, v in enumerate(o["by_weekday"])]))
    add("\n### By hour of request\n")
    top = max((v["left"] for v in o["by_hour"]), default=0)
    add(table(["hour", "judged", "left", "rate", ""],
              [[f"{h:02d}", v["n"], v["left"], pct(v["left"] / v["n"]) if v["n"] else "-", bar(v["left"], top, 25)]
               for h, v in enumerate(o["by_hour"])]))
    add("")
    sp, sv = o["hour_left_vs_wait"], o["hour_left_vs_volume"]
    if sp:
        add(f"- Hours of the day, share who left vs median wait (request -> performed) of those served: "
            f"Spearman rho = {sp['rho']:.2f} (n = {sp['n']} hours, approximate p {pval(sp['p'])}).")
    if sv:
        add(f"- Share who left vs requests received in the hour: rho = {sv['rho']:.2f} "
            f"(approximate p {pval(sv['p'])}).")
    t = o["wait_days_with_vs_without_left"]
    if t:
        add(test_line("Wait of served patients, days with someone leaving vs days with none", t,
                      "days with leavers", "days without"))
    add("\nThe time a patient waited before leaving is not recorded, so the wait of those served in "
        "the same hours stands in for it.\n")


def render_visits(add, ra):
    v = ra.get("visits") or {}
    if not v.get("matched"):
        add("No UPU visit could be matched to the requests (run the `visits` stage).\n")
        return
    iv = v["intervals"]
    add(f"Each request is joined to the UPU presentation it belongs to (the newest one that began no later "
        f"than the request and less than 48 h before it): **{v['matched']} of {v['total']}** requests matched. "
        "Only patients who got an ultrasound request are here: those who left before one was written "
        "cannot be seen.\n")
    add("### Disposition recorded for the visit\n")
    kinds = v["kinds"]
    label = {"home": "went home", "admitted": "admitted", "left_unadvised": "left without notice",
             "transfer": "other unit", "refused": "refused", "other": "other", "unknown": "none"}
    add(table(["disposition", "requests", "share"],
              [[label.get(k, k), n, pct(n / v["matched"])] for k, n in sorted(kinds.items(), key=lambda kv: -kv[1])]))
    add("\nTriage level: " + ", ".join(f"{k} {n}" for k, n in sorted(v["triage"].items(), key=lambda kv: -kv[1])) + ".\n")
    add("### Before the request, and the whole stretch to the report\n")
    for k, name in VISIT_METRICS:
        add(f"**{name[0].upper() + name[1:]}**\n")
        rows = [stat_row("all", iv["all"][k])]
        rows += [stat_row(CLASS_LABEL[c], iv[c][k]) for c in CLASSES]
        rows += [stat_row("triage " + t.split(":", 1)[1], x[k]) for t, x in iv.items() if t.startswith("triage:")]
        add(table(STAT_HEAD, rows))
        add("")
    sb = v["share_before_request"]
    add("Requests written within: " + "; ".join(
        f"{lim} min of arrival {pct((sb[lim] or {}).get('share'))}" for lim in sorted(sb)) + ".\n")

    a = v["admitted"]
    add("### Patients admitted to a ward\n")
    add(f"{a['n']} visits ended in admission, {a['with_admission_time']} with an admission time. "
        "Their whole stay can be timed; patients who went home have no recorded departure time.\n")
    add(table(STAT_HEAD, [stat_row("arrival -> ward admission", a["i_aa"]),
                          stat_row("report signed -> ward admission", a["i_sa"])]))
    add("")
    if a.get("shares"):
        sh = a["shares"]
        add(f"Median share of the time from arrival to admission ({a['complete']} complete stays): "
            f"before the request {pct(sh['before_request'])}, request to report {pct(sh['request_to_signed'])}, "
            f"report to admission {pct(sh['signed_to_admission'])}. The ultrasound stretch is the longest "
            f"of the three in {pct(a['us_dominates'])} of the stays.")
    if a["signed_after_admission"]:
        add(f"- {a['signed_after_admission']} reports were signed after the patient was already admitted.")
    add("")

    lu = v["left_unadvised"]
    add("### Patients who left without notice\n")
    add(f"**{lu['n']} of {v['matched']} visits ({pct(lu['rate'])})** ended with the disposition "
        "*left without notice*. What had happened to their ultrasound request:\n")
    add(table(["request outcome", "visits"], [[k, n] for k, n in sorted(lu["outcomes"].items(), key=lambda kv: -kv[1])]))
    add("")
    signed = lu["outcomes"].get("signed", 0)
    if lu["n"]:
        add(f"{pct(signed / lu['n'])} of them left **after** the report was signed, so the ultrasound wait "
            f"cannot be what made them leave; {pct((lu['n'] - signed) / lu['n'])} left before it was signed.\n")
    rows = [stat_row("left without notice, " + name, lu["intervals"][k]) for k, name in
            (("i_ar", "arrival -> request"), ("i_rp", "request -> performed"),
             ("i_rs", "request -> signed"), ("i_as", "arrival -> signed"))]
    rows += [stat_row("went home, " + name, v["by_kind"].get("home", {}).get(k, {"n": 0}))
             for k, name in (("i_ar", "arrival -> request"), ("i_rp", "request -> performed"),
                             ("i_rs", "request -> signed"))]
    add(table(STAT_HEAD, rows))
    add("")
    for k, name in (("i_ar", "arrival -> request"), ("i_rp", "request -> performed"),
                    ("i_rs", "request -> signed"), ("i_as", "arrival -> signed")):
        add(test_line(f"{name}, left without notice vs went home", lu["tests"][k],
                      "left without notice", "went home"))
    add("")
    add("By shift class:\n")
    add(table(["shift class", "visits", "left without notice", "rate"],
              [[CLASS_LABEL[c], d["n"], d["left"], pct(d["left"] / d["n"]) if d["n"] else "-"]
               for c, d in lu["by_class"].items()]))
    t = lu["test_oncall_vs_day"]
    if t:
        add(f"\n- on-call vs routine hours: {pct(t['x1'] / t['n1'])} ({t['x1']}/{t['n1']}) vs "
            f"{pct(t['x2'] / t['n2'])} ({t['x2']}/{t['n2']}), z = {t['z']:.2f}, p {pval(t['p'])}"
            + (", significant." if t["p"] < 0.05 else ", not significant."))
    add("\nBy hour of the request:\n")
    top = max((d["left"] for d in lu["by_hour"]), default=0)
    add(table(["hour", "visits", "left", "rate", ""],
              [[f"{h:02d}", d["n"], d["left"], pct(d["left"] / d["n"]) if d["n"] else "-", bar(d["left"], top, 25)]
               for h, d in enumerate(lu["by_hour"])]))
    add("\n### The proxy of section 6 against the recorded disposition\n")
    outs = ("signed", "performed_unsigned", "cancelled", "left", "pending")
    add(table(["disposition"] + list(outs),
              [[label.get(k, k)] + [d.get(o, 0) for o in outs] for k, d in v["proxy_vs_disposition"].items()]))
    add("\nA request that was never performed is not always a patient who left: compare the rows.\n")


def render(ra, meta):
    since, until = ra["range"]
    L = []
    add = L.append
    add(f"# UPU ultrasound requests, {since} to {until}\n")
    add(f"*Generated {datetime.now():%Y-%m-%d %H:%M} by `tools/upu_us_stats.py` from "
        f"HippoBridge ({meta.get('ward', 'UPU')} requests, ultrasound laboratory). "
        "All figures are computed from the anonymised `requests.csv`; times are local.*\n")
    if not ra.get("active"):
        add("No requests in the period.")
        return "\n".join(L) + "\n"
    iv = ra["intervals"]
    oc = ra["by_class"]["weeknight"] + ra["by_class"]["weekend"]
    days = len(ra["daily"])

    add("## 1. Summary\n")
    add(f"- **{ra['active']}** UPU ultrasound requests in {days} days "
        f"(**{ra['active'] / days:.1f}/day**), cancelled and never-performed ones included.")
    oo = ra["outcomes"]
    if oo["judged"]:
        add(f"- **{oo['left']}** ({pct(oo['rate'])}) never became an exam: {oo['counts'].get('cancelled', 0)} "
            f"cancelled and {oo['counts'].get('left', 0)} never performed (section 6). This is a guess "
            "at patients who left; the recorded disposition (section 7) is the better measure.")
    vv = ra.get("visits") or {}
    if vv.get("matched"):
        lu = vv["left_unadvised"]
        sg = lu["outcomes"].get("signed", 0)
        add(f"- **{lu['n']}** visits ({pct(lu['rate'])}) ended *left without notice*; "
            f"{sg} of them ({pct(sg / lu['n']) if lu['n'] else '-'}) left after their report was signed. "
            f"Median arrival -> request {dur(vv['intervals']['all']['i_ar'].get('median'))}, "
            f"arrival -> signed {dur(vv['intervals']['all']['i_as'].get('median'))}.")
    add(f"- **{oc}** ({pct(oc / ra['active'])}) were made in the on-call window "
        f"(weekdays 14:00-08:00, weekends 08:00-08:00): {ra['by_class']['weeknight']} on weekday "
        f"nights/evenings, {ra['by_class']['weekend']} at weekends; "
        f"{ra['by_class']['day']} in routine weekday hours (08-14).")
    top = sorted(range(24), key=lambda h: -ra["by_hour"][h])[:3]
    add("- Busiest hours of the day: " + ", ".join(
        f"{h:02d}:00 ({ra['by_hour'][h]})" for h in sorted(top)) + ".")
    s = iv["all"]
    add(f"- Median request -> performed **{dur(s['i_rp'].get('median'))}**, performed -> signed "
        f"**{dur(s['i_ps'].get('median'))}**, request -> signed **{dur(s['i_rs'].get('median'))}** "
        f"(p90 {dur(s['i_rs'].get('p90'))}).")
    for c in ("weeknight", "weekend"):
        x = ra["closing"][c]
        if x["n"]:
            add(f"- {CLASS_LABEL[c]}: {x['signed_by_end']}/{x['n']} requests "
                f"({pct(x['signed_by_end'] / x['n'])}) were signed before the 08:00 that closes their shift.")
    a = ra["tests"].get("i_rs:oncall_vs_day")
    if a:
        add("- Request -> signed, on-call vs routine hours: "
            + ("a significant difference" if a["p"] < 0.05 else "no significant difference")
            + f" (p {pval(a['p'])}, see section 8).")
    add("")

    add("## 2. Data and method\n")
    add(f"- Source: `/api/schedule` (ultrasound laboratory, one call per day, `section == {meta.get('ward', 'UPU')}`) "
        "for the request and performed times and `/api/study/{id}` for the signing time "
        "(the latest validation among the request's studies; signer = that validator).")
    add(f"- Request statuses: " + ", ".join(f"{k} {v}" for k, v in sorted(ra["status"].items())) + ".")
    add("- **Shift day** runs 08:00 -> 08:00. On Saturday, Sunday and listed holidays it is one 24 h "
        "on-call shift (*weekend*). On a working day 08:00-14:00 is *routine* and 14:00 -> 08:00 the "
        "on-call *weeknight*. A request at 03:00 belongs to the previous day's shift.")
    add("- Volume figures count every request, cancelled and never-performed ones too, by request time. "
        "Intervals are in minutes, from requests that were not cancelled and have both end points; "
        f"negative values and values over "
        f"{MAX_MINUTES // 1440} days are counted as data errors and left out.")
    bad = {k: (iv["all"][k]["missing"], iv["all"][k]["negative"], iv["all"][k]["too_long"])
           for k, _ in METRICS}
    add("")
    add(table(["interval", "requests", "missing end point", "negative", f"> {MAX_MINUTES // 1440} d", "usable"],
              [[n, iv["all"][k]["total"], bad[k][0], bad[k][1], bad[k][2], iv["all"][k]["n"]]
               for k, n in METRICS]))
    add("")
    sh = ra["shifts"]
    add(f"- On-call shifts used for per-shift counts: {sh['complete']} complete; "
        f"{len(sh['partial'])} cut by the ends of the period "
        + (f"({', '.join(sh['partial'])})" if sh["partial"] else "") + " are left out of them.\n")

    add("## 3. Volume\n")
    add("### By day\n")
    mx = max(ra["daily"].values())
    rows = []
    for d, n in ra["daily"].items():
        dd = date.fromisoformat(d)
        rows.append([d, WEEKDAYS[dd.weekday()], n, bar(n, mx, 25)])
    add(table(["date", "day", "requests", ""], rows))
    ds = ra["daily_stats"]
    add(f"\nDaily requests: mean {ds['mean']:.1f}, sd {ds['sd']:.1f}, range {ds['min']}-{ds['max']}. "
        f"Variance-to-mean ratio {ds['index']:.2f}"
        + (" (about 1 = as random arrivals would give)" if 0.7 <= ds["index"] <= 1.4 else
           " (above 1: the days are more uneven than random arrivals would give)"
           if ds["index"] > 1.4 else " (below 1: more even than random arrivals)") + ".\n")
    add("### By weekday\n")
    cd = ra["calendar_days"]
    mxw = max(ra["by_weekday"])
    add(table(["day", "requests", ""], [[WEEKDAYS[w], ra["by_weekday"][w], bar(ra["by_weekday"][w], mxw, 25)]
                                        for w in range(7)]))
    if cd["weekday"] and cd["weekend"]:
        add(f"\nPer calendar day: weekdays {cd['weekday']['mean']:.1f} (n = {cd['weekday']['n']} days), "
            f"weekends {cd['weekend']['mean']:.1f} (n = {cd['weekend']['n']} days).")
        add(test_line("Weekend vs weekday days", cd["mw_weekend_vs_weekday"], "weekend", "weekday", "requests"))
    add("")
    add("### By shift class\n")
    add(table(["shift class", "requests", "share"],
              [[CLASS_LABEL[c], ra["by_class"][c], pct(ra["by_class"][c] / ra["active"])] for c in CLASSES]))
    add("")
    add("### Per on-call shift (complete shifts only)\n")
    rows = []
    for c in ("weeknight", "weekend"):
        x = ra["shift_counts"].get(c)
        if x:
            rows.append([CLASS_LABEL[c], x["n"], f1(x["mean"]), f1(x["sd"]), x["min"], x["max"],
                         f"{x['index']:.2f}"])
    add(table(["shift", "shifts", "mean requests", "sd", "min", "max", "variance/mean"], rows))
    add("\nBy priority: " + ", ".join(f"{k} {v}" for k, v in sorted(ra["priority"].items()))
        + f" (urgent {pct(ra['urgent_share'])}).\n")

    add("## 4. Distribution over the day\n")
    add("Request hour, all days; *on-call* counts the requests in the on-call window.\n")
    mxh = max(ra["by_hour"])
    add(table(["hour", "all", "on-call", "share", ""],
              [[f"{h:02d}", ra["by_hour"][h], ra["by_hour_oncall"][h],
                pct(ra["by_hour"][h] / ra["active"]), bar(ra["by_hour"][h], mxh)] for h in range(24)]))
    add("")
    add("Weekday x hour (requests):\n")
    add(table(["day"] + [f"{h:02d}" for h in range(24)] + ["total"],
              [[WEEKDAYS[w]] + ra["weekday_hour"][w] + [sum(ra["weekday_hour"][w])] for w in range(7)]))
    add("")
    night = sum(ra["by_hour"][h] for h in list(range(0, 8)))
    add(f"Between 00:00 and 08:00: {night} requests ({pct(night / ra['active'])}); "
        f"14:00-24:00: {sum(ra['by_hour'][14:])} ({pct(sum(ra['by_hour'][14:]) / ra['active'])}).\n")

    add("## 5. Intervals\n")
    for key, name in METRICS:
        add(f"### {name[0].upper() + name[1:]}\n")
        rows = [stat_row("all", iv["all"][key])]
        rows += [stat_row(CLASS_LABEL[c], iv[c][key]) for c in CLASSES]
        rows += [stat_row("priority " + k.split(":", 1)[1], v[key])
                 for k, v in iv.items() if k.startswith("priority:")]
        add(table(STAT_HEAD, rows))
        add("")
        add("Share finished within: " + "; ".join(
            f"{lim} min {pct((ra['thresholds'][key][lim]['all'] or {}).get('share'))}"
            for lim in sorted(ra["thresholds"][key])) + ".\n")
    add("### By hour of request (median, minutes)\n")
    rows = []
    for h in range(24):
        hi = ra["hour_intervals"][h]
        rows.append([f"{h:02d}", ra["by_hour"][h], hi["i_rp"].get("n", 0), f0(hi["i_rp"].get("median")),
                     hi["i_rs"].get("n", 0), f0(hi["i_rs"].get("median")), f0(hi["i_rs"].get("p90"))])
    add(table(["hour", "requests", "n performed", "request -> performed", "n signed",
               "request -> signed", "p90 request -> signed"], rows))
    add("\nHour in which the reports were signed:\n")
    mxs = max(ra["sign_hour"]) or 1
    add(table(["hour", "signed", ""], [[f"{h:02d}", ra["sign_hour"][h], bar(ra["sign_hour"][h], mxs)]
                                       for h in range(24)]))
    add("")

    add("## 6. Requests that never became an exam\n")
    render_left(add, ra)
    add("## 7. Before and after the ultrasound\n")
    render_visits(add, ra)
    add("## 8. On-call focus and tests\n")
    for c in ("weeknight", "weekend"):
        x = ra["closing"][c]
        add(f"- {CLASS_LABEL[c]}: {x['n']} requests, {x['signed_ever']} signed so far, "
            f"{x['signed_by_end']} signed before the shift ended.")
    add("")
    for key, name in METRICS:
        add(test_line(f"{name}, on-call vs routine hours", ra["tests"][f"{key}:oncall_vs_day"],
                      "on-call", "routine"))
        add(test_line(f"{name}, weekend vs weekday night", ra["tests"][f"{key}:weekend_vs_weeknight"],
                      "weekend", "weekday night"))
    add("")
    for key, name in (("i_rp", "request -> performed"), ("i_rs", "request -> signed")):
        sp = ra["hour_volume_vs_delay"].get(key)
        if sp:
            add(f"- Hours of the day, requests received vs median {name}: Spearman rho = {sp['rho']:.2f} "
                f"(n = {sp['n']} hours, approximate p {pval(sp['p'])}).")
    add("\nThe Mann-Whitney test compares whole distributions without assuming a shape; "
        "P(a > b) is the chance that a random request of group a took longer than one of group b "
        "(0.5 = no difference). Medians carry 95 % bootstrap intervals (2000 resamples, fixed seed).\n")

    add("## 9. Signers\n")
    add("Signers are labelled by workload; the labels are not stable between runs of other periods.\n")
    add(table(["signer", "reports", "on-call share", "median performed -> signed", "median request -> signed"],
              [[s["label"], s["n"], pct(s["oncall_share"]), dur(s["i_ps"].get("median")),
                dur(s["i_rs"].get("median"))] for s in ra["signers"]]))
    add("")

    add("## 10. Limits\n")
    add("- *Performed* is the time entered in Hipocrate (by hand or from the modality), not a measured "
        "start of the scan; a missing or late entry lengthens request -> performed.")
    add("- *Signed* is the validation time of the report; a request with several studies uses the latest, "
        "and a request still unsigned today counts as missing, so recent days look slower than they are.")
    add("- `requested_by` is the attending physician, so the report cannot say who actually ordered the scan.")
    add("- The visit is found through the patient's presentation list; the departure time of a patient who "
        "goes home is not recorded in the pages HippoBridge reads, so report -> leaving exists only for "
        "admitted patients. Patients who left before a request was written are not in the data at all.")
    add("- Public holidays are treated as weekdays unless given with `--holidays`.")
    add("- The tests assume independent requests; consecutive requests share a radiologist and a queue, "
        "so p-values are optimistic.\n")
    add("## 11. Reproduction\n")
    add(f"```\ntools/upu_us_stats.py all --since {since} --until {until} --out <dir>   # fetch, visits, analyze\n```")
    return "\n".join(L) + "\n"


def default_json(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    raise TypeError(type(o))


def analyze(args):
    meta_path = os.path.join(args.out, "meta.json")
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
    since = date.fromisoformat(args.since or meta.get("since") or sys.exit("--since needed"))
    until = date.fromisoformat(args.until or meta.get("until") or sys.exit("--until needed"))
    holidays = frozenset(date.fromisoformat(h) for h in args.holidays.split(",") if h.strip())
    recs = load_requests(args.out, holidays)
    recs = [r for r in recs if since <= r["t_req"].date() <= until]
    as_of = parse_dt((meta.get("fetched_at") or "").replace("T", " ")[:16]) or datetime.now()
    ra = analyze_data(recs, since, until, holidays, as_of)
    with open(os.path.join(args.out, "stats.json"), "w") as f:
        json.dump(ra, f, indent=1, default=default_json, ensure_ascii=False)
    with open(os.path.join(args.out, "report.md"), "w", encoding="utf-8") as f:
        f.write(render(ra, meta))
    log(f"{len(recs)} requests analysed; wrote {args.out}/stats.json and report.md")


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("stage", choices=("fetch", "visits", "analyze", "all"))
    ap.add_argument("--month", help="YYYY-MM: shortcut for the whole month (to --until if given)")
    ap.add_argument("--since", help="first request day, YYYY-MM-DD")
    ap.add_argument("--until", help="last request day, YYYY-MM-DD")
    ap.add_argument("--out", default="_testing_/upu-us-stats", help="output directory")
    ap.add_argument("--ward", default="UPU", help="ward (the schedule's section), default UPU")
    ap.add_argument("--holidays", default="", help="comma-separated YYYY-MM-DD treated as weekends")
    ap.add_argument("--url", default=BASE_URL)
    ap.add_argument("--resume", action="store_true",
                    help="trust the cache: do not read again studies that were unsigned")
    ap.add_argument("--refresh", action="store_true", help="bypass the server's schedule cache")
    ap.add_argument("--pause-schedule", type=float, default=2.0)
    ap.add_argument("--pause-study", type=float, default=1.0)
    ap.add_argument("--pause-visit", type=float, default=0.5)
    ap.add_argument("-u", "--username", default=os.getenv("HYP_USER"))
    ap.add_argument("-w", "--password", default=os.getenv("HYP_PASS"))
    args = ap.parse_args()
    if args.month:
        y, m = map(int, args.month.split("-"))
        args.since = args.since or date(y, m, 1).isoformat()
        args.until = args.until or ((date(y + (m == 12), m % 12 + 1, 1)) - timedelta(days=1)).isoformat()
    if args.stage in ("fetch", "all"):
        if not (args.since and args.until):
            sys.exit("--since and --until (or --month) are needed")
        if not (args.username and args.password):
            args.username, args.password = worklist_creds()
        if not (args.username and args.password):
            sys.exit("No credentials: set HYP_USER/HYP_PASS or worklist.cfg [worklist]")
        asyncio.run(fetch(args))
    if args.stage in ("visits", "all"):
        if not (args.username and args.password):
            args.username, args.password = worklist_creds()
        if not (args.username and args.password):
            sys.exit("No credentials: set HYP_USER/HYP_PASS or worklist.cfg [worklist]")
        asyncio.run(fetch_visits(args))
    if args.stage in ("analyze", "all"):
        analyze(args)


if __name__ == "__main__":
    main()
