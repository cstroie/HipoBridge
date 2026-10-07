#!/usr/bin/env python3
"""
Backfill the search index with historical CT/MRI/US reports.

Walks back week by week, lists CT, MRI and US requests (separately, max 200 each)
via the running server's /api/schedule, skips reports already in search.db and
fetches the rest with /api/study/{id}?justification=0 — the server's own
fetch hook does the indexing. No summarization. Sequential and throttled so
Hipocrate is not hammered.

--since takes a date (2024-01-01) or a relative span: 1d, 3d, 1w.

Credentials: --username/--password, else HYP_USER / HYP_PASS, else
[worklist] username/password from worklist.cfg.
"""
import argparse
import asyncio
import configparser
import json
import os
import re
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta

import aiohttp

BASE_URL = os.getenv("HIPPOBRIDGE_URL", "http://127.0.0.1:44660")
MODALITIES = {"ct": "26", "mri": "32", "us": "28"}
LIMIT = 200
# High-volume modalities are always listed one day at a time instead of
# weekly-then-split-on-cap, so the row cap is never hit by a full week.
DAILY = {"us"}


def parse_since(v):
    m = re.fullmatch(r"(\d+)([dw])", v)
    if m:
        return date.today() - timedelta(days=int(m[1]) * (7 if m[2] == "w" else 1))
    return date.fromisoformat(v)


def worklist_creds():
    cfg = configparser.ConfigParser()
    cfg.read(os.path.join(os.path.dirname(__file__), "..", "worklist.cfg"))
    return (cfg.get("worklist", "username", fallback=None),
            cfg.get("worklist", "password", fallback=None))


def log(msg):
    print(f"{datetime.now():%H:%M:%S} {msg}", flush=True)


class Gentle:
    """Sequential GETs with a fixed pause and backoff retry on failure."""

    def __init__(self, session, pause_schedule, pause_study):
        self.s = session
        self.pause_schedule = pause_schedule
        self.pause_study = pause_study
        self.consecutive_errors = 0

    async def get(self, path, params, pause):
        for attempt in range(4):
            await asyncio.sleep(pause if attempt == 0 else 10 * 2 ** attempt)
            try:
                async with self.s.get(BASE_URL + path, params=params) as r:
                    if r.status == 401:
                        sys.exit("401 Unauthorized: check HYP_USER/HYP_PASS")
                    if r.status < 500:
                        data = await r.json()
                        self.consecutive_errors = 0
                        return data
                    log(f"  HTTP {r.status} on {path} {params}")
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
                log(f"  {type(e).__name__} on {path} {params}")
        self.consecutive_errors += 1
        if self.consecutive_errors >= 5:
            sys.exit("Too many consecutive failures, aborting (re-run with --resume)")
        return None


def indexed_ids(db_path):
    if not os.path.exists(db_path):
        sys.exit(f"{db_path} not found; is [cache] dir correct?")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return {r[0] for r in con.execute(
            "SELECT source_id FROM documents WHERE kind='imaging'")}
    finally:
        con.close()


async def list_requests(g, lab_id, start, end):
    """Rows for [start, end]; splits into days if the row cap is hit."""
    data = await g.get("/api/schedule", {
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "lab_id": lab_id, "limit": LIMIT}, g.pause_schedule)
    if data is None:
        return None
    rows = data.get("requests") or []
    if len(rows) >= LIMIT:
        if start == end:
            log(f"  WARNING {start} lab {lab_id}: day hit the {LIMIT} cap, may be truncated")
            return rows
        rows, d = [], start
        while d <= end:
            part = await list_requests(g, lab_id, d, d)
            if part is None:
                return None
            rows += part
            d += timedelta(days=1)
    return rows


async def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--since", default="2019-01-01",
                    help="YYYY-MM-DD or relative: 1d, 3d, 1w")
    ap.add_argument("--until", default=date.today().isoformat())
    ap.add_argument("--modality", choices=list(MODALITIES), action="append")
    ap.add_argument("--cache-dir", default="/var/tmp/hbcache/",
                    help="[cache] dir; search.db is read from here")
    ap.add_argument("--state", default="backfill_search.state",
                    help="checkpoint file for --resume")
    ap.add_argument("--status", default="ended",
                    help="comma-separated status values to fetch (default: "
                         "ended = 'Terminata', i.e. finalized reports only)")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pause-schedule", type=float, default=2.0)
    ap.add_argument("--pause-study", type=float, default=1.0)
    ap.add_argument("-u", "--username", default=os.getenv("HYP_USER"))
    ap.add_argument("-w", "--password", default=os.getenv("HYP_PASS"))
    args = ap.parse_args()
    if not (args.username and args.password):
        args.username, args.password = worklist_creds()
    if not (args.username and args.password):
        sys.exit("No credentials: set HYP_USER/HYP_PASS or worklist.cfg [worklist]")

    since = parse_since(args.since)
    until = date.fromisoformat(args.until)
    mods = args.modality or list(MODALITIES)
    statuses = set(args.status.split(","))
    # Windows are Mon-Sun, newest first, clipped to [since, until].
    end = until
    if args.resume and os.path.exists(args.state):
        end = min(end, date.fromisoformat(open(args.state).read().strip()))
        log(f"Resuming before {end}")

    done = indexed_ids(os.path.join(args.cache_dir, "search.db"))
    end0 = end
    total_days = (end - since).days + 1
    log(f"Interval {since} .. {end} ({total_days} days, newest first, weekly windows)")
    log(f"Modalities: {', '.join(m.upper() for m in mods)}; fetching only status "
        f"{{{', '.join(sorted(statuses))}}}; row cap {LIMIT}; "
        f"{'DRY RUN, nothing fetched' if args.dry_run else 'live'}")
    log(f"{len(done)} imaging documents already indexed")
    keys = ("listed", "indexed", "other_status", "to_fetch", "new", "no_text", "failed")
    tot = dict.fromkeys(keys, 0)
    t0 = time.monotonic()

    def fmt(c):
        parts = [f"listed={c['listed']}", f"already_indexed={c['indexed']}",
                 f"not_in_status={c['other_status']}"]
        if args.dry_run:
            parts.append(f"would_fetch={c['to_fetch']}")
        else:
            parts += [f"new={c['new']}", f"no_report_text={c['no_text']}",
                      f"failed={c['failed']}"]
        return " ".join(parts)

    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(
            headers={"Authorization": aiohttp.encode_basic_auth(
                args.username, args.password)},
            timeout=timeout) as session:
        g = Gentle(session, args.pause_schedule, args.pause_study)
        while end >= since:
            start = max(since, end - timedelta(days=end.weekday()))
            w = dict.fromkeys(keys, 0)
            seen, ok = set(), True
            log(f"Window {start}..{end}")
            for mod in mods:
                if mod in DAILY:
                    rows, d = [], start
                    while d <= end and rows is not None:
                        part = await list_requests(g, MODALITIES[mod], d, d)
                        rows = None if part is None else rows + part
                        d += timedelta(days=1)
                else:
                    rows = await list_requests(g, MODALITIES[mod], start, end)
                if rows is None:
                    ok = False
                    log(f"  {mod.upper()}: listing FAILED, window will be retried with --resume")
                    continue
                m = dict.fromkeys(keys, 0)
                by_status, todo = {}, []
                for row in rows:
                    rid = str(row.get("request_id") or "")
                    if not rid or rid in seen:
                        continue
                    seen.add(rid)
                    m["listed"] += 1
                    st = row.get("status") or "?"
                    by_status[st] = by_status.get(st, 0) + 1
                    if rid in done:
                        m["indexed"] += 1
                    elif st not in statuses:
                        m["other_status"] += 1
                    else:
                        todo.append(rid)
                m["to_fetch"] = len(todo)
                log(f"  {mod.upper()}: {m['listed']} exams listed ("
                    + ", ".join(f"{k} {v}" for k, v in sorted(by_status.items()))
                    + f"); {m['indexed']} already indexed, {len(todo)} to fetch")
                if not args.dry_run:
                    for n, rid in enumerate(todo, 1):
                        res = await g.get(f"/api/study/{rid}",
                                          {"justification": "0"}, g.pause_study)
                        if res and res.get("status") == "success":
                            # Report not written yet: the server doesn't index it.
                            if any(st.get("result") for st in res.get("studies") or []):
                                m["new"] += 1
                                done.add(rid)
                            else:
                                m["no_text"] += 1
                        else:
                            m["failed"] += 1
                        if n % 25 == 0 and n < len(todo):
                            log(f"    {mod.upper()} fetching {n}/{len(todo)} "
                                f"(new={m['new']} no_text={m['no_text']} failed={m['failed']})")
                    log(f"  {mod.upper()} done: new={m['new']} no_report_text={m['no_text']} "
                        f"failed={m['failed']}")
                for k in keys:
                    w[k] += m[k]
            for k in keys:
                tot[k] += w[k]
            elapsed = time.monotonic() - t0
            log(f"Window total {start}..{end}: {fmt(w)}")
            log(f"Progress: {(end0 - start).days + 1}/{total_days} days, "
                f"running total {fmt(tot)}, elapsed {timedelta(seconds=int(elapsed))}")
            if ok and not args.dry_run:
                open(args.state, "w").write((start - timedelta(days=1)).isoformat())
            end = start - timedelta(days=1)

    log(f"Done in {timedelta(seconds=int(time.monotonic() - t0))}: {fmt(tot)}")

if __name__ == "__main__":
    asyncio.run(main())
