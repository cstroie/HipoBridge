#!/usr/bin/env python3
"""
UPU ultrasound: which patients were called in by a hospital physician?

Plan: docs/upu_called_patients_plan.md. Built on tools/upu_us_stats.py, whose
`fetch` stage lists the requests (its cache.jsonl is this tool's input).

  fetch    for each UPU ultrasound request of the source cache: the request
           (/api/request/{id}), the patient's history (/api/patient/{pid})
           and the presentation it belongs to (/api/presentation/{prid}).
           Kept in <out>/cache.jsonl, raw, on this machine only.
  fields   how often each field is filled and the values of the categorical
           ones (physicians never printed), plus the frequent words of the
           free texts (a word or pair seen at least --min-count times).
  texts    for each fetched request: its ultrasound report (/api/study) and the
           epicrisis of the last discharge within 90 days (/api/checkout),
           kept in <out>/texts.jsonl (mode 600, this machine only).
  analyze  features and rule scores per request -> <out>/called.csv
           (salted hashes, flags and times only) and <out>/report.md.

Privacy: <out>/cache.jsonl holds patient ids, clinical texts and physician
names; keep <out> on this machine (under _testing_/, gitignored). Nothing
the analysis writes holds a name, CNP, id or free text.

Example:
  tools/upu_called.py fetch --source _testing_/upu-2026-10 --out _testing_/upu-called
  tools/upu_called.py fields --out _testing_/upu-called
  tools/upu_called.py analyze --out _testing_/upu-called
"""
import argparse
import asyncio
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import upu_us_stats as base  # noqa: E402

log = base.log
parse_dt = base.parse_dt
pres_time = base.pres_time


# ----------------------------------------------------------------------- fetch

REQUEST_KEYS = ("section", "justification", "clinical_situation", "diagnosis_referral",
                "investigation", "clinical_data", "special_indications", "guideline_decision",
                "prior_imaging", "physician_curant", "physician_solicitant", "requester",
                "date_time", "region", "previous")
PRESENTATION_KEYS = ("date_time", "transport_type", "transport_vehicle", "section", "medic",
                     "reason", "decision", "consult_section", "treatment", "triage_code",
                     "triage", "triage_time", "consult_type", "consults", "antecedents",
                     "diagnosis")
HISTORY_KEYS = ("kind", "type", "start", "end", "section_in", "section_out", "medic_in",
                "medic_out", "diagnosis", "presentation_id", "checkin_id")


def any_time(v):
    return pres_time(v) or parse_dt(v)


def pick_presentation(req_time, history):
    """The UPU presentation a request belongs to: the newest one that began no
    later than the request and less than 48 h before it (as upu_us_stats), by
    the history's presentation rows (admissions carry a presentation id too,
    so only `kind == presentation` counts). None when the history cannot tell."""
    starts = []
    for h in history:
        prid, t = h.get("presentation_id"), any_time(h.get("start"))
        if h.get("kind") == "presentation" and prid and t:
            starts.append((t, str(prid)))
    starts.sort(reverse=True)
    for t, prid in starts:
        if t <= req_time:
            return prid if req_time - t <= timedelta(hours=48) else None
    return None


async def fetch(args):
    import aiohttp
    src = base.load_cache(os.path.join(args.source, "cache.jsonl"))
    todo_src = [r for r in src.values() if (r.get("mod") or "us") == "us"]
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "cache.jsonl")
    cache = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                cache[r["id"]] = r
    todo = [r for r in todo_src if r["id"] not in cache or not cache[r["id"]].get("done")]
    todo.sort(key=lambda r: r["requested"])
    if args.limit:
        todo = todo[:args.limit]
    log(f"Fetch: {len(todo)} of {len(todo_src)} ultrasound requests to look up")
    patients = {}                         # pid -> patient payload, in memory
    t0 = time.monotonic()
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(args.username, args.password),
                                     timeout=timeout) as session:
        g = base.Gentle(session, args.url)
        for n, srec in enumerate(todo, 1):
            rec = {k: srec.get(k) for k in ("id", "requested", "performed", "signed", "status",
                                             "v_arrival", "v_triage", "v_decision",
                                             "v_admission")}
            rq = await g.get(f"/api/request/{srec['id']}", {}, args.pause)
            if rq is None:
                continue
            req = rq.get("request") or {}
            rec["request"] = {k: req.get(k) for k in REQUEST_KEYS}
            rec["request"]["performed_at"] = rq.get("performed_at")
            pat = rq.get("patient") or {}
            pid = pat.get("id")
            rec["pid"] = pid
            rec["age"], rec["sex"] = pat.get("age"), pat.get("gender")
            if pid:
                if pid not in patients:
                    p = await g.get(f"/api/patient/{pid}", {}, args.pause)
                    if p is None:
                        continue
                    patients[pid] = p
                p = patients[pid]
                hist = [{k: h.get(k) for k in HISTORY_KEYS} for h in (p.get("history") or [])]
                rec["history"] = hist
                req_time = parse_dt(srec["requested"])
                prid = pick_presentation(req_time, hist) if req_time else None
                pr = None
                if prid:
                    pr = await g.get(f"/api/presentation/{prid}", {}, args.pause)
                    if pr is None:
                        continue
                    rec["match"] = "history"
                elif req_time:
                    # The old tool's way: the patient's presentations, newest first.
                    ids = p.get("presentation") or []
                    ids = ids if isinstance(ids, list) else [ids]
                    ids = sorted((i for i in ids if str(i).isdigit()), key=int, reverse=True)
                    failed = False
                    for i in ids[:4]:
                        d = await g.get(f"/api/presentation/{i}", {}, args.pause)
                        if d is None:
                            failed = True
                            break
                        t = pres_time((d.get("presentation") or {}).get("date_time"))
                        if t is None or t > req_time:
                            continue
                        if req_time - t <= timedelta(hours=48):
                            pr, prid = d, str(i)
                            rec["match"] = "list"
                        break
                    if failed:
                        continue
                rec["prid"] = prid
                if pr:
                    pp = pr.get("presentation") or {}
                    rec["presentation"] = {k: pp.get(k) for k in PRESENTATION_KEYS}
                    enc = pr.get("encounter") or {}
                    rec["encounter"] = {k: enc.get(k) for k in
                                        ("diagnosis", "working", "secondary", "reason",
                                         "notes", "disposition", "end")}
            rec["done"] = True
            cache[rec["id"]] = rec
            if n % 25 == 0:
                save(path, cache)
                el = time.monotonic() - t0
                log(f"    {n}/{len(todo)} ({el / n:.1f} s each, "
                    f"~{timedelta(seconds=int(el / n * (len(todo) - n)))} left)")
    save(path, cache)
    os.chmod(path, 0o600)
    log(f"Fetch done in {timedelta(seconds=int(time.monotonic() - t0))}: {len(cache)} cached")


async def fetch_texts(args):
    """Two texts per request, kept in <out>/texts.jsonl (mode 600, this machine
    only): the ultrasound's own report, and the epicrisis of the patient's last
    discharge within 90 days before the visit (its ward and dates too)."""
    import aiohttp
    recs = {r["id"]: r for r in load(args.out)}
    path = os.path.join(args.out, "texts.jsonl")
    texts = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                t = json.loads(line)
                texts[t["id"]] = t
    def arrival_of(r):
        return parse_dt(r.get("v_arrival")) or pres_time((r.get("presentation") or {})
                                                          .get("date_time"))

    def needs(r):
        t = texts.get(r["id"])
        if t is None:
            return True
        # A discharge letter not looked for yet (an older run used v_arrival only).
        return (not t.get("co_checked") and not t.get("epicrisis")
                and last_discharge(r, arrival_of(r)) is not None)

    todo = sorted((r for r in recs.values() if r.get("done") and needs(r)),
                  key=lambda r: r["requested"])
    if args.limit:
        todo = todo[:args.limit]
    log(f"Texts: {len(todo)} of {len(recs)} requests to look up")
    checkouts, patients = {}, {}
    t0 = time.monotonic()
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(args.username, args.password),
                                     timeout=timeout) as session:
        g = base.Gentle(session, args.url)
        for n, r in enumerate(todo, 1):
            t = texts.get(r["id"])
            if t is None:
                t = {"id": r["id"], "report": "", "epicrisis": "", "co_ward": "", "co_out": ""}
                st = await g.get(f"/api/study/{r['id']}", {"justification": "0"}, args.pause)
                if st is None:
                    continue
                t["report"] = "\n\n".join(s.get("result") or "" for s in st.get("studies") or [])
            arrival = arrival_of(r)
            last = last_discharge(r, arrival)
            pid = r.get("pid")
            if last and pid:
                if pid not in patients:
                    p = await g.get(f"/api/patient/{pid}", {}, args.pause)
                    if p is None:
                        continue
                    ids = p.get("checkout") or []
                    ids = ids if isinstance(ids, list) else [ids]
                    patients[pid] = sorted((i for i in ids if str(i).isdigit()), key=int,
                                           reverse=True)
                for coid in patients[pid][:6]:
                    if coid not in checkouts:
                        co = await g.get(f"/api/checkout/{coid}", {}, args.pause)
                        if co is None:
                            break
                        checkouts[coid] = co
                    co = checkouts[coid]
                    out = any_time(co.get("checkout.date_time") or
                                   (co.get("checkout") or {}).get("date_time"))
                    if out and abs((out - last).total_seconds()) <= 36 * 3600:
                        c = co.get("checkout") if isinstance(co.get("checkout"), dict) else {}
                        t["epicrisis"] = co.get("checkout.epicrisis") or c.get("epicrisis") or ""
                        t["co_ward"] = co.get("checkout.ward") or c.get("ward") or ""
                        t["co_out"] = base.iso(out)
                        break
            t["co_checked"] = True
            texts[r["id"]] = t
            if n % 25 == 0:
                save(path, texts)
                el = time.monotonic() - t0
                log(f"    {n}/{len(todo)} ({el / n:.1f} s each, "
                    f"~{timedelta(seconds=int(el / n * (len(todo) - n)))} left)")
    save(path, texts)
    os.chmod(path, 0o600)
    log(f"Texts done in {timedelta(seconds=int(time.monotonic() - t0))}: {len(texts)} kept")


def last_discharge(r, arrival):
    """End of the patient's last admission (continuous or day) that ended in
    the 90 days before `arrival`, or None."""
    if arrival is None:
        return None
    best = None
    for h in r.get("history") or []:
        if h.get("kind") not in ("admission", "day_admission"):
            continue
        en = any_time(h.get("end"))
        if en and en <= arrival and arrival - en <= timedelta(days=90):
            best = en if best is None or en > best else best
    return best


def save(path, cache):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in cache.values():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def load(out):
    with open(os.path.join(out, "cache.jsonl"), encoding="utf-8") as f:
        return [json.loads(line) for line in f]


# ---------------------------------------------------------------------- fields

def fold(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


WORD = re.compile(r"[a-z][a-z0-9]+")
PERSON_FIELDS = {"medic", "medic_in", "medic_out", "physician_curant", "physician_solicitant",
                 "requester", "triage_nurse"}
TEXT_FIELDS = {"justification", "reason", "clinical_situation", "diagnosis_referral",
               "clinical_data", "special_indications", "prior_imaging", "antecedents",
               "diagnosis", "treatment", "working", "secondary", "notes"}


def fields(args):
    recs = load(args.out)
    log(f"{len(recs)} requests")
    filled, values, words = Counter(), defaultdict(Counter), defaultdict(Counter)

    def visit(group, d):
        for k, v in (d or {}).items():
            key = f"{group}.{k}"
            if v not in (None, "", [], {}):
                filled[key] += 1
            if k in PERSON_FIELDS or k in ("code", "performed_at", "date_time", "start", "end", "triage_time",
                                            "presentation_id", "checkin_id", "previous",
                                            "consults"):
                continue
            if k in TEXT_FIELDS or k == "justification":
                texts = v if isinstance(v, list) else [v]
                for t in texts:
                    toks = WORD.findall(fold(t))
                    for w in set(toks):
                        words[key][w] += 1
                    for a, b in set(zip(toks, toks[1:])):
                        words[key][f"{a} {b}"] += 1
            elif isinstance(v, (str, int)) or v is None:
                values[key][fold(v)[:60]] += 1

    hist_n = Counter()
    for r in recs:
        visit("request", r.get("request"))
        visit("presentation", r.get("presentation"))
        visit("encounter", r.get("encounter"))
        for c in (r.get("presentation") or {}).get("consults") or []:
            visit("consult", c)
        prev = (r.get("request") or {}).get("previous") or []
        hist_n["previous"] += len(prev)
        for p in prev:
            values["previous.code"][fold(p.get("code"))] += 1
        for h in r.get("history") or []:
            visit("history", h)
            hist_n["history"] += 1

    print(f"# Fields of {len(recs)} UPU ultrasound requests\n")
    print("## Filled\n")
    for k, c in sorted(filled.items()):
        print(f"- {k}: {c}")
    print(f"\nhistory entries {hist_n['history']}, previous requests {hist_n['previous']}\n")
    print("## Categorical values (top 25)\n")
    for k, cnt in sorted(values.items()):
        if len(cnt) > 400:
            print(f"- {k}: {len(cnt)} distinct, skipped")
            continue
        print(f"- {k}: " + "; ".join(f"{v or '∅'} {c}" for v, c in cnt.most_common(25)))
    print(f"\n## Frequent words (at least {args.min_count})\n")
    for k, cnt in sorted(words.items()):
        top = [(w, c) for w, c in cnt.most_common(args.top) if c >= args.min_count]
        print(f"- {k}: " + "; ".join(f"{w} {c}" for w, c in top))


# --------------------------------------------------------------------- analyze

TITLES = {"dr", "prof", "conf", "sl", "as", "med", "univ"}
AGE_BANDS = ("<1", "1-5", "6-17", "18-64", "65+", "?")
HOME, ADMITTED = "plecat din upu la domiciliu", "internare"
WEEKDAYS = base.WEEKDAYS


def norm_name(s):
    """A physician's name as a comparable key: folded, titles dropped, tokens
    sorted ("DR. POPESCU ION" == "Ion Popescu")."""
    return " ".join(sorted(w for w in re.findall(r"[a-z]+", fold(s)) if w not in TITLES))


def age_years(v):
    m = re.fullmatch(r"\s*(\d+)\s*([ymd]?)\s*", str(v or ""))
    if not m:
        return None
    n, u = int(m.group(1)), m.group(2) or "y"
    return n if u == "y" else n / 12 if u == "m" else n / 365


def age_band(a):
    if a is None:
        return "?"
    return "<1" if a < 1 else "1-5" if a < 6 else "6-17" if a < 18 else "18-64" if a < 65 else "65+"


def triage_level(code):
    m = re.search(r"(\d)", str(code or ""))
    return int(m.group(1)) if m else None


def ward_name(s):
    """A ward without its floor/state suffix ("pediatrie 2 etaj iii(inactiva)")."""
    w = fold(s)
    w = re.sub(r"\s*\(.*?\)", "", w)
    w = re.sub(r"\s+etaj\s+\w+$", "", w)
    return re.sub(r"[^a-z0-9 ]+", " ", w).split(" a")[0].strip() if w.startswith("chirurgie") \
        else re.sub(r"[^a-z0-9 ]+", " ", w).strip()


def staff_map(recs):
    """norm name -> its home: 'upu' or the ward it works in most, learnt from
    who attends UPU visits and who admits/discharges on which ward."""
    upu, ward = Counter(), defaultdict(Counter)
    seen_hist = set()
    for r in recs:
        m = norm_name((r.get("presentation") or {}).get("medic"))
        if m:
            upu[m] += 1
        for h in r.get("history") or []:
            key = (h.get("kind"), h.get("start"), h.get("presentation_id"), h.get("checkin_id"))
            if key in seen_hist:
                continue
            seen_hist.add(key)
            for who, sec in (("medic_in", "section_in"), ("medic_out", "section_out")):
                n, w = norm_name(h.get(who)), ward_name(h.get(sec))
                if not n or not w:
                    continue
                if w == "upu":
                    upu[n] += 1
                else:
                    ward[n][w] += 1
    home = {}
    for n in set(upu) | set(ward):
        u, best = upu.get(n, 0), ward[n].most_common(1)
        if best and best[0][1] > u:
            home[n] = best[0][0]
        elif u:
            home[n] = "upu"
    return home


CONTROL_WORDS = re.compile(
    r"\b(control|reevaluar\w*|reevalua\w*|recomandar\w*|la indicatia|trimis\w*|chemat\w*|"
    r"programat\w*|post\s*-?\s*op\w*|postoperator\w*|dupa interventi\w*|monitorizar\w*|"
    r"urmarir\w*|evaluare periodica|cunoscut\w* cu|in evidenta)\b")


def text_flags(q):
    """Words of a planned control in the request's texts (a flag; the text is
    never written)."""
    t = fold(" ".join(str(q.get(k) or "") for k in
                      ("justification", "clinical_situation", "clinical_data", "diagnosis_referral",
                       "special_indications", "prior_imaging")))
    return {"text_control": bool(CONTROL_WORDS.search(t))}


REPORT_FLAGS = {
    "rep_compare": r"comparativ|fata de (examinarea|ecografia|ex\b|precedent|anterior)|"
                   r"examinarea (anterioara|precedenta)|in evolutie|evolutie favorabil|"
                   r"in regresie|remis|persista|persistenta|in scadere|in crestere fata",
    "rep_postop": r"post\s*-?\s*op|postoperator|status post|s\.?p\.? apendic|apendicectom|"
                  r"operat|interventi\w* chirurg|laparoscop|laparotom|plaga|drenaj|bont",
    "rep_normal": r"aspect (ecografic )?normal|ecografic normal|fara modificari|fara particularitati|"
                  r"in limite normale|nu se (vizualizeaza|evidentiaza|decelea)\w* (colecti|lichid)|"
                  r"fara lichid liber|fara colectii",
}
EPI_FLAGS = {
    "epi_control": r"control|reevalu|reveni|revine|se (va )?prezenta|prezentare la",
    "epi_us": r"ecograf|\beco\b",
    "epi_upu": r"\bupu\b|urgent|camera de garda|\bgarda\b",
}
DAYS_RE = re.compile(r"(?:peste|la|dupa|in)\s+(\d{1,2})\s*(?:-\s*\d{1,2}\s*)?(zile|zi|saptaman\w*)")


def text_features(t, arrival):
    """Flags from the request's texts (texts.jsonl); never the text itself."""
    f = {k: False for k in (*REPORT_FLAGS, *EPI_FLAGS)}
    f.update(has_report=False, has_epicrisis=False, epi_surgery=False, epi_days=None,
             epi_on_time=False)
    if not t:
        return f
    rep, epi = fold(t.get("report")), fold(t.get("epicrisis"))
    f["has_report"], f["has_epicrisis"] = bool(rep), bool(epi)
    for k, rx in REPORT_FLAGS.items():
        f[k] = bool(re.search(rx, rep))
    for k, rx in EPI_FLAGS.items():
        f[k] = bool(re.search(rx, epi))
    f["epi_surgery"] = "chirurg" in fold(t.get("co_ward"))
    out = parse_dt(t.get("co_out"))
    m = DAYS_RE.search(epi)
    if m:
        n = int(m.group(1)) * (7 if m.group(2).startswith("sapt") else 1)
        f["epi_days"] = n
        if out and arrival:
            f["epi_on_time"] = abs((arrival - out).days - n) <= 3
    return f


def surgery_on_call(recs, holidays=frozenset()):
    """shift date -> Counter of norm names admitting to a surgery ward during
    that day's on-call hours (weekday 14-08, weekend/holiday 08-08): a derived
    surgical on-call roster, from every admission in the histories."""
    roster, seen = defaultdict(lambda: defaultdict(set)), set()
    for r in recs:
        for h in r.get("history") or []:
            if h.get("kind") != "admission" or "chirurg" not in ward_name(h.get("section_in")):
                continue
            st = any_time(h.get("start"))
            key = (h.get("checkin_id"), h.get("start"))
            if st is None or key in seen:
                continue
            seen.add(key)
            cls, d = base.shift_of(st, holidays)
            n = norm_name(h.get("medic_in"))
            if cls != "day" and n:
                roster[d][n].add(r.get("pid"))
    return roster


def roster_from_csv(paths, home):
    """A real on-call roster (date,weekday,line1,line2,... of surnames, an
    optional initial: "Popescu O") -> the shape of surgery_on_call(). Each
    surname is matched to the surgery-ward physicians learnt from the data;
    a cut name ("Atud…") or one matching nobody is reported, not guessed."""
    import csv
    surgeons = [n for n, w in home.items() if "chirurg" in w]
    roster, missing = defaultdict(lambda: defaultdict(set)), Counter()
    rows = []
    for path in paths.split(","):
        with open(path, encoding="utf-8") as fh:
            rows += list(csv.DictReader(fh))
    for row in rows:
        d = datetime.fromisoformat(row["date"]).date()
        for col, cell in row.items():
            if not col or not col.startswith("line") or col.endswith("_cut") or not cell:
                continue
            parts = norm_name(cell).split()
            if not parts:
                continue
            sur = max(parts, key=len)
            ini = [x for x in parts if x != sur and len(x) == 1]
            hits = [n for n in surgeons if sur in n.split()
                    and all(any(t.startswith(i) for t in n.split() if t != sur) for i in ini)]
            if not hits:
                missing[cell] += 1
            for n in hits:
                roster[d][n].add("roster")
    if missing:
        log("Roster names matching no surgeon in the data: " + ", ".join(sorted(missing)))
    return roster


def on_call(roster, d, pid):
    """Names on call on shift date d, learnt from other patients' admissions."""
    return {n for n, pids in (roster.get(d) or {}).items() if pids - {pid}}


def features(r, home, holidays=frozenset(), texts=None, prev_us=None, roster=None,
             real_roster=False):
    q = r.get("request") or {}
    pr = r.get("presentation") or {}
    arrival = parse_dt(r.get("v_arrival")) or pres_time(pr.get("date_time"))
    requested = parse_dt(r.get("requested"))
    f = {"id": r["id"], "requested": r.get("requested") or "", "arrival": base.iso(arrival),
         "_pid": r.get("pid")}
    f["matched"] = bool(pr)
    a = age_years(r.get("age"))
    f["age_band"] = age_band(a)
    f["triage"] = triage_level(pr.get("triage_code"))
    f["ambulance"] = "saj" in fold(pr.get("transport_type")) or "smurd" in fold(pr.get("transport_type"))
    f["treated"] = bool(pr.get("treatment"))
    dec = fold(pr.get("decision") or r.get("v_decision"))
    f["home"] = dec == HOME
    f["admitted"] = dec == ADMITTED or bool(r.get("v_admission"))
    f["left"] = "fara aviz" in dec
    f["arr_to_req"] = base.minutes(arrival, requested)
    t = arrival or requested
    f["shift"] = base.shift_of(t, holidays)[0] if t else ""
    f["hour"] = t.hour if t else None
    f["weekday"] = t.weekday() if t else None

    req = norm_name(q.get("requester") or q.get("physician_solicitant"))
    att = norm_name(q.get("physician_curant") or pr.get("medic"))
    f["req_is_attending"] = bool(req) and req == att
    f["req_home"] = home.get(req, "unknown") if req else "none"
    # A ward physician covering a UPU shift orders as UPU does, so only a surgeon counts.
    f["req_outside"] = "chirurg" in f["req_home"]
    f.update(text_flags(q))

    # The patient's history before this arrival.
    last_dis, last_ward, last_kind, last_by_req, open_day = None, "", "", False, False
    last_medics = set()
    upu30 = upu90 = upu365 = 0
    for h in r.get("history") or []:
        kind = h.get("kind")
        st, en = any_time(h.get("start")), any_time(h.get("end"))
        if arrival is None or st is None:
            continue
        if kind == "presentation":
            if str(h.get("presentation_id")) == str(r.get("prid")) or st >= arrival:
                continue
            d = (arrival - st).days
            upu30 += d <= 30
            upu90 += d <= 90
            upu365 += d <= 365
            continue
        if kind not in ("admission", "day_admission"):
            continue
        if st <= arrival and (en is None or en >= arrival - timedelta(hours=1)):
            if kind == "day_admission":
                open_day = True
            continue
        if en and en <= arrival and (last_dis is None or en > last_dis):
            last_dis, last_kind = en, kind
            last_ward = ward_name(h.get("section_out") or h.get("section_in"))
            last_medics = {norm_name(h.get("medic_out")), norm_name(h.get("medic_in"))} - {""}
            last_by_req = bool(req) and req in last_medics
    days = (arrival - last_dis).days if last_dis and arrival else None
    f["days_since_discharge"] = days
    f["dis30"] = days is not None and days <= 30
    f["dis90"] = days is not None and days <= 90
    f["dis_kind"] = last_kind if f["dis90"] else ""
    f["dis_ward"] = last_ward if f["dis90"] else ""
    f["dis_by_requester"] = f["dis90"] and last_by_req
    f["dis_ward_is_req"] = f["dis90"] and f["req_outside"] and last_ward == f["req_home"]
    f["open_day_admission"] = open_day
    f["upu30"], f["upu90"], f["upu365"] = upu30, upu90, upu365
    surg_all = set()
    for h in r.get("history") or []:
        st = any_time(h.get("start"))
        if (h.get("kind") in ("admission", "day_admission") and st and arrival and st < arrival
                and "chirurg" in ward_name(h.get("section_in") or h.get("section_out"))):
            surg_all |= {norm_name(h.get("medic_in")), norm_name(h.get("medic_out"))} - {""}
    f["_surg_all"] = surg_all
    # The surgeon(s) of the child's last surgical stay ended in the 365 days before.
    last365, last_end = set(), None
    for h in r.get("history") or []:
        en = any_time(h.get("end"))
        if (h.get("kind") in ("admission", "day_admission") and en and arrival and en <= arrival
                and arrival - en <= timedelta(days=365)
                and "chirurg" in ward_name(h.get("section_out") or h.get("section_in"))
                and (last_end is None or en > last_end)):
            last_end = en
            last365 = {norm_name(h.get("medic_out")), norm_name(h.get("medic_in"))} - {""}
    f["_surg_last365"] = last365
    # A later admission to surgery (elective: not from this visit, no UPU visit
    # in between): the ultrasound may have been a pre-operative one.
    nxt, nxt_medics, upu_between = None, set(), []
    for h in r.get("history") or []:
        st = any_time(h.get("start"))
        if not st or not arrival or st <= arrival + timedelta(hours=12):
            continue
        if h.get("kind") == "presentation":
            upu_between.append(st)
        elif (h.get("kind") in ("admission", "day_admission")
              and "chirurg" in ward_name(h.get("section_in") or h.get("section_out"))
              and st - arrival <= timedelta(days=30) and (nxt is None or st < nxt)):
            nxt = st
            nxt_medics = {norm_name(h.get("medic_in")), norm_name(h.get("medic_out"))} - {""}
    f["later_surg_days"] = (nxt - arrival).days if nxt else None
    f["later_surg_elective"] = bool(nxt) and not any(t < nxt for t in upu_between) \
        and not f["admitted"]
    f["_later_medics"] = nxt_medics if f["later_surg_elective"] else set()
    f["surg_ever"] = bool(surg_all)
    upu7 = 0
    for h in r.get("history") or []:
        st = any_time(h.get("start"))
        if (h.get("kind") == "presentation" and st and arrival and st < arrival
                and str(h.get("presentation_id")) != str(r.get("prid"))
                and arrival - st <= timedelta(days=7)):
            upu7 += 1
    f["upu7"] = upu7
    f["prev_us_days"] = prev_us
    f["repeat_us7"] = prev_us is not None and prev_us <= 7
    f.update(text_features(texts, arrival))
    f["nonurgent"] = f["home"] and not f["treated"] and not f["ambulance"]
    f["nonurgent_strict"] = f["nonurgent"] and f["rep_normal"]
    f["surg_recent"] = f["dis30"] and ("chirurg" in f["dis_ward"] or f["epi_surgery"])
    # Is the surgeon who treated this patient on call now? None = cannot tell.
    f["own_surgeon_on_call"] = None
    f["roster_known"] = False
    if roster is not None and arrival and "chirurg" in (last_ward or "") and f["dis90"]:
        cls, d = base.shift_of(arrival, holidays)
        on = on_call(roster, d, r.get("pid")) if cls != "day" or real_roster else set()
        if on:
            f["roster_known"] = True
            f["own_surgeon_on_call"] = bool(last_medics & on)
            near = [on_call(roster, x, r.get("pid")) for x in roster
                    if abs((x - d).days) <= 60]
            near = [x for x in near if x]
            f["_chance"] = sum(1 for x in near if last_medics & x) / len(near) if near else 0
    f["_last_medics"] = last_medics if "chirurg" in (last_ward or "") and f["dis90"] else set()

    # B: non-urgent. Triage is not used: most children get code 2 whatever brings them.
    f["fast_req"] = f["arr_to_req"] is not None and 0 <= f["arr_to_req"] <= 15
    # A: arranged, in tiers.
    scheduled = f["epi_on_time"] and (f["epi_control"] or f["epi_us"])
    if f["req_outside"] or open_day or f["dis_by_requester"] or scheduled:
        tier = "definite"
    elif (f["dis30"] and f["nonurgent"]) or (f["repeat_us7"] and f["nonurgent"]) or \
            (f["later_surg_elective"] and f["nonurgent"]) or \
            (f["rep_compare"] and f["nonurgent"] and (f["dis90"] or f["upu30"])):
        tier = "probable"
    elif f["nonurgent_strict"] and (f["dis90"] or f["upu90"] or f["rep_compare"] or f["rep_postop"]):
        tier = "possible"
    else:
        tier = "none"
    f["tier"] = tier
    return f


def previous_us(recs):
    """request id -> days since the same patient's previous UPU ultrasound
    request of another visit, within this data set."""
    by_pid = defaultdict(list)
    for r in recs:
        t = parse_dt(r.get("requested"))
        if r.get("pid") and t:
            by_pid[r["pid"]].append((t, r.get("prid"), r["id"]))
    out = {}
    for items in by_pid.values():
        items.sort()
        for i, (t, prid, rid) in enumerate(items):
            for t0, prid0, _ in reversed(items[:i]):
                if prid0 != prid or prid is None:
                    out[rid] = (t - t0).total_seconds() / 86400
                    break
    return out


def fmt_test(t):
    if not t:
        return "no test"
    p = t.get("p")
    return f"z {t.get('z', 0):.1f}, p {base.pval(p)}" if p is not None else "no test"


def poisson_tail(k, lam):
    """P(X >= k) for X ~ Poisson(lam)."""
    import math
    return 1 - sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k)) if lam else None


def share(n, d):
    return f"{n} ({100 * n / d:.0f}%)" if d else "0"


def crosstab(rows, key_r, key_c, cols=None, rows_order=None):
    c = Counter((key_r(f), key_c(f)) for f in rows)
    rk = rows_order or sorted({k[0] for k in c}, key=str)
    ck = cols or sorted({k[1] for k in c}, key=str)
    head = ["", *map(str, ck), "total"]
    out = []
    for a in rk:
        tot = sum(c[(a, b)] for b in ck)
        out.append([str(a), *(str(c[(a, b)]) for b in ck), str(tot)])
    out.append(["total", *(str(sum(c[(a, b)] for a in rk)) for b in ck), str(len(rows))])
    return base.table(head, out)


TIERS = ("definite", "probable", "possible", "none")


def analyze(args):
    recs = load(args.out)
    holidays = frozenset(d for d in (args.holidays or "").split(",") if d)
    recs = [r for r in recs if (r.get("status") or "") not in base.CANCELLED]
    home = staff_map(recs)
    texts = {}
    tpath = os.path.join(args.out, "texts.jsonl")
    if os.path.exists(tpath):
        with open(tpath, encoding="utf-8") as fh:
            for line in fh:
                t = json.loads(line)
                texts[t["id"]] = t
    prev = previous_us(recs)
    roster = (roster_from_csv(args.roster, home) if args.roster
              else surgery_on_call(recs, holidays))
    feats = [features(r, home, holidays, texts.get(r["id"]), prev.get(r["id"]), roster,
                      bool(args.roster)) for r in recs]
    salt = base.salt_for(args.out)
    cols = [k for k in feats[0] if k != "id" and not k.startswith("_")]
    with open(os.path.join(args.out, "called.csv"), "w", newline="", encoding="utf-8") as fh:
        import csv
        w = csv.writer(fh)
        w.writerow(["rid", *cols])
        for f in feats:
            w.writerow([base.digest(salt, "request", f["id"], 12), *(f[c] for c in cols)])
    write_label_sheet(args, recs)
    md = report(feats, home, args, roster, holidays)
    m_ = [f for f in feats if f["matched"] and (not args.since or f["arrival"][:10] >= args.since)]
    spath = os.path.join(args.out, "surgeons.md")
    with open(spath, "w", encoding="utf-8") as fh:
        fh.write(surgeon_drill(m_, home, roster, display_names(recs), holidays,
                               named=set(named_people(home, [x for x in (args.named or "").split(",")
                                                             if x]))))
    os.chmod(spath, 0o600)
    with open(os.path.join(args.out, "report.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    print(md)


def write_label_sheet(args, recs, n=200, seed=20261102):
    import random
    path = os.path.join(args.out, "label_sheet.csv")
    if os.path.exists(path):
        return
    pool = sorted(r["id"] for r in recs if r.get("presentation"))
    random.Random(seed).shuffle(pool)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("request_id,called_by_physician (y/n/?),specialty,non_urgent (y/n/?),note\n")
        for i in sorted(pool[:n], key=int):
            fh.write(f"{i},,,,\n")
    os.chmod(path, 0o600)


def roster_test(m, roster, holidays):
    """Do surgical patients come back on their own surgeon's on-call shift
    more often than chance? Chance = the share of known on-call shifts that
    surgeon covers; observed = the share of the patient's visits (on shifts
    whose roster is known) where they are on call."""
    obs = exp = n = 0
    rows = []
    for f in m:
        if not f["_last_medics"] or not f["roster_known"]:
            continue
        p = f.get("_chance", 0)
        n += 1
        obs += bool(f["own_surgeon_on_call"])
        exp += p
        rows.append(f)
    return n, obs, exp, rows


def named_people(home, surnames):
    """Surname list -> {norm name: code A, B, ...} for surgeons whose home is
    a surgery ward (the code follows the order given)."""
    out = {}
    for i, sn in enumerate(surnames):
        for n, w in home.items():
            if sn in n.split() and "chirurg" in w:
                out[n] = chr(ord("A") + i)
    return out


def named_section(add, m, roster, named, holidays, real=False):
    """What the named surgeons' patients and on-call shifts look like."""
    codes = sorted(set(named.values()))
    add("\n## Named surgeons\n")
    add(f"{len(codes)} surgeons named by the owner, coded {', '.join(codes)} (names are not "
        "written). Their patient = treated by one of them (admitted or discharged, any stay "
        "on a surgery ward) before this visit, or admitted electively by one of them in the "
        "30 days after it.\n")
    def grp(f):
        if (f["_surg_all"] | f["_later_medics"]) & set(named):
            return "their patient"
        return "other surgical patient" if f["surg_ever"] else "no surgical stay"
    add(crosstab(m, grp, lambda f: "non-urgent" if f["nonurgent"] else "urgent/other",
                 cols=["non-urgent", "urgent/other"],
                 rows_order=["their patient", "other surgical patient", "no surgical stay"]))
    add("\nBy shift class:\n")
    add(crosstab(m, grp, lambda f: f["shift"], cols=list(base.CLASSES),
                 rows_order=["their patient", "other surgical patient", "no surgical stay"]))
    def pts(f):
        return f["_surg_all"] | f["_later_medics"]
    rows, groups = [], {}
    for k in codes:
        mine = {n for n, c_ in named.items() if c_ == k}
        groups[k] = [f for f in m if pts(f) & mine]
    groups["all named"] = [f for f in m if pts(f) & set(named)]
    top = max(codes, key=lambda k: len(groups[k])) if codes else None
    if top:
        groups[f"named without {top}"] = [f for f in m if pts(f) & {n for n, c_ in named.items()
                                                                     if c_ != top}]
    groups["other surgical"] = [f for f in m if f["surg_ever"] and not pts(f) & set(named)]
    groups["no surgical stay"] = [f for f in m if not f["surg_ever"] and not f["_later_medics"]]
    base_ = groups["no surgical stay"]
    bx = sum(f["nonurgent"] for f in base_)
    for k, v in groups.items():
        x = sum(f["nonurgent"] for f in v)
        t = base.two_proportions(x, len(v), bx, len(base_)) if v and k != "no surgical stay" else None
        rows.append([k, str(len(v)), share(x, len(v)), fmt_test(t) if t else ""])
    add("\nNon-urgent share of their patients' visits (test against children with no "
        f"surgical stay; {top} treats the most children):\n")
    add(base.table(["patients of", "visits", "non-urgent", "vs no surgical stay"], rows))

    # Shift level: on-call shifts of the period with a known roster.
    days = {datetime.fromisoformat(f["arrival"][:10]).date() for f in m if f["arrival"]}
    lo, hi = min(days), max(days)
    shift_rows = defaultdict(lambda: {"all": 0, "nonurgent": 0, "strict": 0})
    for f in m:
        t = parse_dt(f["arrival"])
        if not t:
            continue
        cls, d = base.shift_of(t, holidays)
        if cls == "day" and not real:
            continue
        x = shift_rows[(cls, d)]
        x["all"] += 1
        x["nonurgent"] += f["nonurgent"]
        x["strict"] += f["nonurgent_strict"]
    groups = defaultdict(list)
    unknown = 0
    for (cls, d), x in shift_rows.items():
        on = set((roster.get(d) or {}).keys())
        if not on:
            unknown += 1
            continue
        hours = (base.shift_bounds(cls, d)[1] - base.shift_bounds(cls, d)[0]).total_seconds() / 3600
        key = ("named on call" if on & set(named) else "other surgeon", cls)
        groups[key].append((x, hours))
    add(f"\nShifts {lo} to {hi} with a known surgeon on call "
        f"({'the given roster; a weekday morning counts as its date' if real else 'learnt from admissions'}): "
        f"{sum(len(v) for v in groups.values())}; unknown: {unknown}. UPU ultrasounds per "
        "shift:\n")
    rows = []
    for key in sorted(groups):
        v = groups[key]
        n = len(v)
        rows.append([key[0], key[1], str(n),
                     f"{sum(x['all'] for x, _ in v) / n:.1f}",
                     f"{sum(x['nonurgent'] for x, _ in v) / n:.1f}",
                     f"{sum(x['strict'] for x, _ in v) / n:.1f}"])
    add(base.table(["surgeon on call", "shift", "shifts", "US", "non-urgent", "strict"], rows))
    spread = defaultdict(list)
    for (cls, d), x in shift_rows.items():
        spread[cls].append(x["all"])
    import statistics
    add("\nShift-to-shift spread (sd of US per shift): " + "; ".join(
        f"{k} {statistics.stdev(v):.1f}" for k, v in sorted(spread.items()) if len(v) > 1) +
        ". A difference of a few children a shift cannot be detected with this many shifts.\n")
    for code in codes:
        mine = {n for n, c_ in named.items() if c_ == code}
        k = [(x, cls) for (cls, d), x in shift_rows.items() if mine & set((roster.get(d) or {}).keys())]
        if k:
            add(f"\n- {code}: {len(k)} on-call shifts known, US per shift "
                f"{sum(x['all'] for x, _ in k) / len(k):.1f}, non-urgent "
                f"{sum(x['nonurgent'] for x, _ in k) / len(k):.1f}")
    add("")


def wilson(x, n, z=1.96):
    if not n:
        return (0.0, 0.0)
    import math
    p = x / n
    d = 1 + z * z / n
    c_ = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c_ - h), min(1.0, c_ + h))


def display_names(recs):
    """norm name -> the name as Hipocrate writes it (most common spelling)."""
    seen = defaultdict(Counter)
    for r in recs:
        for h in r.get("history") or []:
            for k in ("medic_in", "medic_out"):
                v = (h.get(k) or "").strip()
                if v:
                    seen[norm_name(v)][re.sub(r"^dr\.?\s*", "", v, flags=re.I).title()] += 1
    return {n: c.most_common(1)[0][0] for n, c in seen.items()}


def surgeon_drill(m, home, roster, shown, holidays=frozenset(), window=365, named=()):
    """Per surgeon: the UPU ultrasound visits of their patients (discharged by
    them from surgery in the 90 days before, or admitted electively by them in
    the 30 days after), the non-urgent share against the pooled share (a
    funnel test), mornings, repeats, pre-op scans and returns on their own
    on-call shifts. Names: for the owner's eyes only (surgeons.md, mode 600)."""
    import math
    by = defaultdict(list)
    for f in m:
        for n in (f["_surg_last365"] if window == 365 else f["_last_medics"]) | f["_later_medics"]:
            if "chirurg" in home.get(n, ""):
                by[n].append(f)
    allv = [f for v in by.values() for f in v]
    p0 = sum(f["nonurgent"] for f in allv) / len(allv) if allv else 0
    rows = []
    for n, v in by.items():
        k = len(v)
        x = sum(f["nonurgent"] for f in v)
        exp = k * p0
        z = (x - exp) / math.sqrt(k * p0 * (1 - p0)) if k and 0 < p0 < 1 else 0
        pv = 0.5 * math.erfc(z / math.sqrt(2))          # one-sided: above the pool
        lo, hi = wilson(x, k)
        morning = sum(1 for f in v if f["nonurgent"] and f["shift"] == "day")
        rep = sum(1 for f in v if f["repeat_us7"])
        preop = sum(1 for f in v if n in f["_later_medics"])
        oc = [f for f in v if f["roster_known"] and n in f["_last_medics"]]   # 90-day test
        on = sum(1 for f in oc if f["own_surgeon_on_call"])
        shifts = sum(1 for d in roster if n in roster[d]) if roster else 0
        rows.append((x - exp, n, k, x, lo, hi, z, pv, morning, rep, preop, on, len(oc), shifts))
    # The same per child: the first visit of each child per surgeon.
    firsts = {}
    for n, v in by.items():
        seen = {}
        for f in sorted(v, key=lambda f: f["arrival"]):
            seen.setdefault(f["_pid"], f)
        firsts[n] = seen
    allc = [f for seen in firsts.values() for f in seen.values()]
    p1 = sum(f["nonurgent"] for f in allc) / len(allc) if allc else 0
    child = {}
    for n, seen in firsts.items():
        k, x = len(seen), sum(f["nonurgent"] for f in seen.values())
        z = (x - k * p1) / math.sqrt(k * p1 * (1 - p1)) if k and 0 < p1 < 1 else 0
        child[n] = (k, x, 0.5 * math.erfc(z / math.sqrt(2)))
    rows = [r + child[r[1]] for r in rows]
    rows.sort(reverse=True)
    L = ["# UPU ultrasound by surgeon: FOR THE OWNER ONLY (names; never share or commit)\n",
         f"{len(allv)} visits attributed to {len(by)} surgeons. A visit belongs to the surgeon "
         "of the child's last surgical stay (ended in the 365 days before it), or who admitted the "
         "child electively in the 30 days after (a pre-op scan done through UPU). Pooled "
         f"non-urgent share {100 * p0:.0f}%. **Excess** = non-urgent visits above what the "
         "pooled share predicts for that many visits; **p** = one-sided funnel test (with "
         f"{len(by)} surgeons, about {0.05 * len(by):.1f} would pass p < 0.05 by chance alone).\n",
         "This shows whose patients come back to UPU for non-urgent scans, not who told them "
         "to come: no record says that.\n"]
    L.append(base.table(
        ["surgeon", "visits", "non-urgent", "95% CI", "excess", "p", "mornings", "repeat <=7 d",
         "pre-op", "back on own on-call", "on-call shifts", "children", "non-urgent (children)",
         "p (children)"],
        [[shown.get(n, n), str(k), f"{x} ({100 * x / k:.0f}%)", f"{100 * lo:.0f}-{100 * hi:.0f}%",
          f"{ex:+.1f}", base.pval(pv), str(mo), str(rp), str(po),
          f"{on}/{noc}" if noc else "-", str(sh) if roster else "-", str(ck),
          f"{cx} ({100 * cx / ck:.0f}%)" if ck else "-", base.pval(cp)]
         for ex, n, k, x, lo, hi, z, pv, mo, rp, po, on, noc, sh, ck, cx, cp in rows]))
    if roster:
        L.append(oncall_drill(m, roster, shown, holidays))
    for label, col in (("visits", 7), ("children", 16)):
        ps = sorted(r[col] for r in rows)
        bh = [p for i, p in enumerate(ps, 1) if p <= 0.05 * i / len(ps)]
        L.append(f"\nBy {label}: false-discovery control (Benjamini-Hochberg, 5%, {len(ps)} "
                 f"surgeons): {len(bh)} pass; smallest p {base.pval(ps[0]) if ps else '-'}.")
        if named:
            sel = sorted((r[col], shown.get(r[1], r[1])) for r in rows if r[1] in named)
            holm, k = [], len(sel)
            for i, (p, who) in enumerate(sel):
                if p <= 0.05 / (k - i):
                    holm.append(f"{who} (p {base.pval(p)})")
                else:
                    break
            L.append(f"By {label}: Holm over the {k} surgeons named by the owner (exploratory: "
                     "named from experience of the same period): "
                     + (", ".join(holm) if holm else "none") + " pass.")
    L.append("")
    return "\n".join(L) + "\n"


def oncall_drill(m, roster, shown, holidays=frozenset()):
    """Every rostered surgeon: the UPU ultrasounds of their on-call shifts
    (the weekday morning of their date counted too) against the mean of all
    shifts of the same class, with a t value over their shifts."""
    import math
    import statistics
    per = defaultdict(lambda: {"all": 0, "nu": 0, "own": 0})
    for f in m:
        t = parse_dt(f["arrival"])
        if not t:
            continue
        cls, d = base.shift_of(t, holidays)
        x = per[(cls, d)]
        x["all"] += 1
        x["nu"] += f["nonurgent"]
    days = {d for _, d in per}
    if not days:
        return ""
    lo, hi = min(days), max(days)
    mean = {}
    for cls in base.CLASSES:
        v = [x for (c_, _), x in per.items() if c_ == cls]
        if v:
            mean[cls] = (statistics.mean(x["all"] for x in v), statistics.mean(x["nu"] for x in v))
    people = defaultdict(list)
    for d, names in roster.items():
        if lo <= d <= hi:
            for n in names:
                people[n].append(d)
    rows = []
    for n, ds in people.items():
        ex_all, ex_nu, k = [], [], 0
        for d in ds:
            for cls in base.CLASSES:
                if (cls, d) in per and cls in mean:
                    x = per[(cls, d)]
                    ex_all.append(x["all"] - mean[cls][0])
                    ex_nu.append(x["nu"] - mean[cls][1])
            k += 1
        if not ex_nu:
            continue
        mu = statistics.mean(ex_nu)
        sd = statistics.stdev(ex_nu) if len(ex_nu) > 1 else 0
        tval = mu / (sd / math.sqrt(len(ex_nu))) if sd else 0
        rows.append((mu, n, k, len(ex_nu), statistics.mean(ex_all), mu, tval))
    rows.sort(reverse=True)
    out = ["\n## On call: every rostered surgeon\n",
           f"Shifts {lo} to {hi}. Each surgeon's on-call dates from the roster; for each date its "
           "shifts in the data (a weekday: the morning 08-14 and the night 14-08; a weekend or "
           "holiday: 08-08) compared with the mean of all shifts of the same class. **Excess** = "
           "mean difference per shift; **t** = excess over its standard error (|t| > 2 is worth a "
           "look, with this many surgeons one or two will pass by chance). Only roster names that "
           "match a surgeon who admits patients are here (Linia 1 mostly).\n"]
    out.append(base.table(["surgeon", "dates", "shifts", "US excess / shift",
                           "non-urgent excess / shift", "t (non-urgent)"],
                          [[shown.get(n, n), str(k), str(ns), f"{ea:+.1f}", f"{en:+.1f}",
                            f"{tv:+.1f}"] for _, n, k, ns, ea, en, tv in rows]))
    return "\n".join(out)


def bottom_line(m, nd, days, roster, home, args):
    """The findings first, in plain words, from the same numbers as below."""
    n = len(m)
    nu = sum(f["nonurgent"] for f in m)
    traced = [f for f in m if f["tier"] in ("definite", "probable") and f["nonurgent"]]
    surg = sum(1 for f in traced if f["later_surg_elective"] or
               any(w in (f["dis_ward"] or "") for w in ("chirurg", "ortoped")))
    rep = sum(1 for f in traced if f["repeat_us7"] and not (
        f["later_surg_elective"] or any(w in (f["dis_ward"] or "") for w in ("chirurg", "ortoped"))))
    rest = [f for f in m if f not in traced]
    td, rd = sum(f["shift"] == "day" for f in traced), sum(f["shift"] == "day" for f in rest)
    t = base.two_proportions(td, len(traced), rd, len(rest))
    out = ["## Bottom line\n",
           f"Period {days[0] if days else ''} to {days[-1] if days else ''}: {n} UPU "
           f"ultrasounds, {n / nd:.0f} a day.\n",
           f"1. **Half of the UPU ultrasound load is non-urgent, whoever sent the child:** "
           f"{nu} of {n} ({100 * nu / n:.0f}%), about {nu / nd:.0f} a day, went home untreated "
           "and not by ambulance. Triage does not show it (most children get code 2).",
           f"2. **Called-in controls that the records can trace: about {len(traced) / nd:.1f} "
           f"a day** ({len(traced)} visits), a lower bound. {surg} point to surgery or "
           "orthopaedics (a stay there in the last 30 days, or an elective surgery admission "
           f"in the 30 days after); {rep} are a second UPU scan within 7 days (\"come back "
           "tomorrow\", sender unknown). The rest cannot be seen: the surgeon's part is never "
           "recorded when the child goes home.",
           f"3. **They come in the mornings:** {share(td, len(traced))} in the weekday 08-14 "
           f"shift, against {share(rd, len(rest))} of all other visits ({fmt_test(t)}): the "
           "hours the day-care cabinet is free."]
    named = named_people(home, [x for x in (args.named or "").split(",") if x])
    if named:
        mine = [f for f in m if (f["_surg_all"] | f["_later_medics"]) & set(named)]
        none = [f for f in m if not f["surg_ever"] and not f["_later_medics"]]
        other = [f for f in m if f["surg_ever"] and not (f["_surg_all"] | f["_later_medics"])
                 & set(named)]
        x1, x2, x3 = (sum(f["nonurgent"] for f in g) for g in (mine, none, other))
        t1 = base.two_proportions(x1, len(mine), x2, len(none))
        t2 = base.two_proportions(x1, len(mine), x3, len(other))
        out.append(f"4. **The named surgeons' patients are non-urgent more often:** "
                   f"{share(x1, len(mine))} of their {len(mine)} visits, against "
                   f"{share(x2, len(none))} for children with no surgical stay ({fmt_test(t1)}); "
                   f"not clearly more than other surgeons' patients, {share(x3, len(other))} "
                   f"({fmt_test(t2)}).")
    if roster:
        rows = [f for f in m if f["_last_medics"] and f["roster_known"]]
        obs = sum(bool(f["own_surgeon_on_call"]) for f in rows)
        exp = sum(f.get("_chance", 0) for f in rows)
        if exp:
            pt = poisson_tail(obs, exp)
            word = ("more often than chance" if pt < 0.05 else "a hint only")
            out.append(f"5. **Own surgeon on call, {word}:** surgical patients came back "
                       f"while their own surgeon was on call {obs} times, against {exp:.1f} "
                       f"by chance (n {len(rows)}, P {pt:.2f}). Extra "
                       "volume on a named surgeon's shift is too small to detect against the "
                       "shift-to-shift spread.")
    out.append("\n**What would settle it:** the owner's labels (label_sheet.csv) and, in "
               "November, asking at each UPU ultrasound on the named surgeons' on-call shifts "
               "who sent the child.\n")
    return "\n".join(out)


def report(feats, home, args, roster=None, holidays=frozenset()):
    L = []
    add = L.append
    m = [f for f in feats if f["matched"]]
    if args.since:
        m = [f for f in m if f["arrival"][:10] >= args.since]
    days = sorted({f["arrival"][:10] for f in m if f["arrival"]})
    nd = len(days) or 1
    add("# UPU ultrasound: patients called in by a hospital physician\n")
    add(bottom_line(m, nd, days, roster, home, args))
    add("## Data and definitions\n")
    add(f"Requests (not cancelled): {len(feats)}; matched to a UPU visit: {len(m)}; "
        f"days: {nd} ({days[0] if days else ''} to {days[-1] if days else ''}).\n")
    add("Tiers of A (arranged): **definite** = ordered by a surgeon, or the patient is in an open day admission, or the requester discharged "
        "the patient in the last 90 days, or this visit falls on the control day its last "
        "discharge letter names; **probable** = a non-urgent visit of a patient discharged "
        "from any ward in the last 30 days, or scanned in UPU in the last 7 days, or whose "
        "report compares with an earlier exam (after a discharge or UPU visit), or who is "
        "admitted to surgery electively in the 30 days after; **possible** "
        "= a strictly non-urgent visit of a patient discharged or seen in UPU in the last 90 "
        "days, or whose report compares or mentions surgery.\nB (non-urgent) = went home, no treatment, not brought by ambulance (strict: and the "
        "ultrasound report reads normal). Triage is not used: most children get code 2.\n")

    add("## Requester\n")
    add(crosstab(m, lambda f: ("upu" if f["req_home"] == "upu" else
                               "ward" if f["req_outside"] else f["req_home"]),
                 lambda f: "attending" if f["req_is_attending"] else "other",
                 cols=["attending", "other"]))
    staff = Counter(v for v in home.values())
    add(f"\nPhysicians learnt: {len(home)} ({staff['upu']} UPU, "
        f"{len(home) - staff['upu']} on wards).\n")

    add("## Tiers x non-urgent (A x B)\n")
    add(crosstab(m, lambda f: f["tier"], lambda f: "non-urgent" if f["nonurgent"] else "urgent/other",
                 cols=["non-urgent", "urgent/other"], rows_order=list(TIERS)))
    add("\nStrict non-urgent:\n")
    add(crosstab(m, lambda f: f["tier"], lambda f: "strict" if f["nonurgent_strict"] else "-",
                 cols=["strict", "-"], rows_order=list(TIERS)))

    add("\n## Per day\n")
    per = defaultdict(Counter)
    for f in m:
        per[f["arrival"][:10]][f["tier"]] += 1
        per[f["arrival"][:10]]["all"] += 1
        if f["tier"] in ("definite", "probable") and f["nonurgent"]:
            per[f["arrival"][:10]]["target"] += 1
    rows = []
    for d in days:
        c = per[d]
        rows.append([d, WEEKDAYS[datetime.fromisoformat(d).weekday()], str(c["all"]),
                     *(str(c[t]) for t in TIERS[:3]), str(c["target"])])
    add(base.table(["day", "", "all", *TIERS[:3], "def+prob & non-urgent"], rows))
    mean = lambda k: sum(per[d][k] for d in days) / nd
    add(f"\nMean a day: all {mean('all'):.1f}, definite {mean('definite'):.1f}, probable "
        f"{mean('probable'):.1f}, possible {mean('possible'):.1f}, "
        f"definite+probable and non-urgent {mean('target'):.1f}.\n")

    add("## By shift class\n")
    add(crosstab(m, lambda f: f["shift"], lambda f: f["tier"], cols=list(TIERS),
                 rows_order=list(base.CLASSES)))
    P = [f for f in m if f["tier"] == "probable"]
    if P:
        trig = Counter()
        for f in P:
            t = []
            if f["dis30"]:
                t.append("discharge <=30 d: " + (f["dis_ward"] or "?"))
            if f["repeat_us7"]:
                t.append("repeat US <=7 d")
            if f["later_surg_elective"]:
                t.append("later elective surgery")
            if f["rep_compare"]:
                t.append("report compares")
            trig[" + ".join(t)] += 1
        add("\n### What makes the probable ones probable\n")
        add(base.table(["trigger", "n"], [[k, str(v)] for k, v in trig.most_common()]))
        pd_ = sum(f["shift"] == "day" for f in P)
        rest = [f for f in m if f["tier"] != "probable"]
        rd = sum(f["shift"] == "day" for f in rest)
        t = base.two_proportions(pd_, len(P), rd, len(rest))
        add(f"\nProbable ones in the weekday 08-14 shift: {share(pd_, len(P))}, against "
            f"{share(rd, len(rest))} of the rest ({fmt_test(t)}).\n")
    add("\n## By age band\n")
    add(crosstab(m, lambda f: f["age_band"], lambda f: f["tier"], cols=list(TIERS),
                 rows_order=[b for b in AGE_BANDS if any(f["age_band"] == b for f in m)]))
    add("\n## Specialty of the definite ones (requester's ward, else the discharging ward)\n")
    add(crosstab([f for f in m if f["tier"] == "definite"],
                 lambda f: f["req_home"] if f["req_outside"] else (f["dis_ward"] or "open day adm."),
                 lambda f: "non-urgent" if f["nonurgent"] else "urgent/other",
                 cols=["non-urgent", "urgent/other"]))
    add("\n## Arrival hour (weekdays), all vs definite+probable\n")
    add("Caution: almost nobody is registered 07:00-08:00 and a burst follows at 08:00-08:20 "
        "(also a smaller one at 20:00): arrivals around a shift change are registered at its "
        "start. The 08:00 peak is partly that, not scheduled arrivals.\n")
    rows = []
    for h in range(24):
        a = [f for f in m if f["hour"] == h and f["weekday"] is not None and f["weekday"] < 5]
        t = [f for f in a if f["tier"] in ("definite", "probable")]
        rows.append([f"{h:02d}", str(len(a)), str(len(t)), base.bar(len(t), 40, 20)])
    add(base.table(["hour", "all", "def+prob", ""], rows))
    if roster:
        n, obs, exp, rows = roster_test(m, roster, holidays)
        add("\n## Own surgeon on call?\n")
        add(f"{'Given' if args.roster else 'Derived'} surgical on-call roster: {len(roster)} on-call shifts with a known "
            f"admitting surgeon. UPU ultrasounds of patients discharged from surgery in the "
            f"last 90 days, arriving on an on-call shift with a known roster (learnt from other "
            f"patients; chance from the shifts within 60 days): {n}. The surgeon who treated them "
            f"was on call on {obs} of them; chance alone would give {exp:.1f}"
            + (f" (ratio {obs / exp:.2f}; P(at least {obs} by chance) "
               f"{poisson_tail(obs, exp):.2f})." if exp else ".") + "\n")
        first = {}
        for f in sorted(rows, key=lambda f: f["arrival"]):
            first.setdefault(f["_pid"], f)
        o1 = sum(bool(f["own_surgeon_on_call"]) for f in first.values())
        e1 = sum(f.get("_chance", 0) for f in first.values())
        if e1:
            add(f"One visit per child (the first): {o1} of {len(first)} children, against "
                f"{e1:.1f} by chance (P {poisson_tail(o1, e1):.3f}).\n")
        if rows:
            add(crosstab(rows, lambda f: "own surgeon on call" if f["own_surgeon_on_call"]
                         else "not on call", lambda f: "non-urgent" if f["nonurgent"] else
                         "urgent/other", cols=["non-urgent", "urgent/other"]))
    named = named_people(home, [x for x in (args.named or "").split(",") if x])
    if named and roster:
        named_section(add, m, roster, named, holidays, bool(args.roster))
    add("\n## Signals\n")
    sig = ("req_outside", "text_control", "open_day_admission",
           "fast_req", "repeat_us7", "upu7", "later_surg_elective", "surg_recent", "has_report", "rep_compare", "rep_postop",
           "rep_normal", "has_epicrisis", "epi_control", "epi_us", "epi_upu", "epi_surgery",
           "epi_on_time", "dis_by_requester", "dis_ward_is_req", "dis30",
           "dis90", "nonurgent", "nonurgent_strict", "treated", "ambulance", "home", "admitted",
           "left")
    add(base.table(["signal", "n"], [[s, share(sum(1 for f in m if f[s]), len(m))] for s in sig]))
    add("\nPrior UPU visits in 90 days: " + "; ".join(
        f"{k}: {v}" for k, v in sorted(Counter(min(f['upu90'], 3) for f in m).items())) + " (3 = 3+)\n")
    add("\nTriage codes: " + "; ".join(f"{k}: {v}" for k, v in
                                      sorted(Counter(f["triage"] for f in m).items(), key=str)) + "\n")
    return "\n".join(L)


# --------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("stage", choices=("fetch", "texts", "fields", "analyze"))
    ap.add_argument("--source", default="_testing_/upu-2026-10",
                    help="upu_us_stats output directory whose cache lists the requests")
    ap.add_argument("--out", default="_testing_/upu-called")
    ap.add_argument("--url", default=base.BASE_URL)
    ap.add_argument("--pause", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=0, help="fetch at most this many")
    ap.add_argument("--min-count", type=int, default=5)
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--named", default="",
                    help="comma-separated surgeon surnames to examine (never written out)")
    ap.add_argument("--roster", help="CSV of the surgical on-call roster (date,weekday,line1,"
                    "line2,...), used instead of the one derived from admissions")
    ap.add_argument("--since", help="first arrival day counted (YYYY-MM-DD): leave out a "
                    "partial first day")
    ap.add_argument("--holidays", default="", help="comma-separated YYYY-MM-DD treated as weekends")
    ap.add_argument("--username")
    ap.add_argument("--password")
    args = ap.parse_args()
    if args.stage in ("fetch", "texts"):
        u, p = base.worklist_creds()
        args.username = args.username or os.getenv("HYP_USER") or u
        args.password = args.password or os.getenv("HYP_PASS") or p
        asyncio.run(fetch(args) if args.stage == "fetch" else fetch_texts(args))
    elif args.stage == "fields":
        fields(args)
    else:
        analyze(args)


if __name__ == "__main__":
    main()
