#!/usr/bin/env python3
"""Local full-text search index over epicrisis and imaging report text.

Hipocrate has no full-text search of its own (see docs/SITE_SURVEY.md) —
files/search.asp and the schedule's PARA_TextCautare filter both match only
patient name/CNP, never report body text. This module builds HippoBridge's
own index instead, scoped to whatever epicrisis/imaging text has already
passed through this server, not a bulk crawl of all of Hipocrate.

`instance`/`schedule_index()` below are module-level (mirrors hippoclient.py's
`url_cache = URLCache()` singleton pattern) rather than living on a hippobridge.py
global, because the actual write hook lives in hippoclient.py's
HippoClientCheckout/HippoClientImagingStudy.fetch_and_parse() overrides — the
single choke point shared by both the /api/* and /fhir/* routes that
construct those clients (the frontend only ever calls the /fhir/* ones).
hippobridge.py just sets `search.instance` in init_app() and reads it
back for the /api/search/text route and periodic cleanup.

SQLite FTS5, tokenized with unicode61 remove_diacritics 2 so a search for
"cauza" also matches "cauzâ"/"cauză" as typed inconsistently in Romanian
clinical text. All blocking sqlite3 calls run via run_in_executor, mirroring
how sqlcache.SqliteCache is already kept off the event loop.
"""

import asyncio
import json
import logging
import re
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

logger = logging.getLogger('SearchIndex')

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    patient_cnp TEXT,
    patient_name TEXT,
    updated_at REAL NOT NULL,
    UNIQUE(kind, source_id)
);
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    text, tokenize="unicode61 remove_diacritics 2"
);
CREATE TABLE IF NOT EXISTS passages (
    id INTEGER PRIMARY KEY,
    doc_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    section TEXT
);
CREATE INDEX IF NOT EXISTS passages_doc ON passages(doc_id, seq);
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
    text, tokenize="unicode61 remove_diacritics 2"
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

# Columns added after the first release; ALTERed in on open (additive — the
# index is never rebuilt from empty). NULL `status` marks a row indexed before
# the metadata existed: not 'final', so never returned until re-parsed.
_META_COLUMNS = {
    'doc_date': 'TEXT',      # ISO date: study date (imaging) or discharge date (epicrisis)
    'modality': 'TEXT',      # DICOM code (MR, CT, US, CR…), imaging only
    'title': 'TEXT',         # exam name, imaging only
    'status': 'TEXT',        # 'final' | 'draft'
    'identifiers': 'TEXT',   # JSON {label: value}: what names the patient in the text
}

# FTS5 query-syntax characters that would otherwise be interpreted as
# operators (", *, -, (, ) etc.) rather than literal search text.
_TOKEN_RE = re.compile(r'[\w]+', re.UNICODE)


def _fold(text: str) -> str:
    """Lowercase and strip diacritics, like the FTS tokenizer (ș/ş/s all alike)."""
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower())
                   if not unicodedata.combining(c))


def parse_query(query: str) -> list:
    """Query string → list of slots. A slot is a list of alternatives, each a
    list of folded tokens (several tokens = a phrase). `"hernie de disc"` is a
    phrase, `meningiom|meningioame` two alternatives of one slot, anything
    else one single-token slot. Input is reduced to word characters, so FTS5
    syntax can't leak through."""
    slots = []
    for m in re.finditer(r'"([^"]*)"|(\S+)', query):
        raw = m.group(1) if m.group(1) is not None else m.group(2)
        alts = []
        for alt in (raw.split('|') if m.group(2) else [raw]):
            toks = _TOKEN_RE.findall(_fold(alt))
            if toks:
                alts.append(toks)
        if alts:
            slots.append(alts)
    return slots


def _slot_fts(slot: list) -> str:
    # Quoted so "and"/"or"/"not"/"near" are literal. A single token is a
    # prefix match; a phrase is exact (only its last word is a prefix).
    parts = []
    for toks in slot:
        parts.append(f'"{toks[0]}"*' if len(toks) == 1 else f'"{" ".join(toks)}" *')
    return parts[0] if len(parts) == 1 else '(' + ' OR '.join(parts) + ')'


def _slots_in(folded: str, slots: list) -> set:
    """Indexes of the slots present in already-folded text."""
    words = _TOKEN_RE.findall(folded)
    found = set()
    for i, slot in enumerate(slots):
        for toks in slot:
            n = len(toks)
            if any(words[j:j + n - 1] == toks[:-1] and words[j + n - 1].startswith(toks[-1])
                   for j in range(len(words) - n + 1)):
                found.add(i)
                break
    return found


_SENT_RE = re.compile(r'(?<=[.!?;:])\s+|\n+')
_CHUNK_CHARS = 600      # aim for passages of 500-900 characters
_CHUNK_MAX = 900
# Report section headers, folded. Matched at the start of a sentence/line,
# optionally wrapped in Markdown emphasis: "**Concluzii:**".
_SECTION_RE = re.compile(
    r'^[\s*_#>-]*(descriere|concluzii|concluzie|tehnica|indicatie|indicatii|comparatie|'
    r'rezultat|rezultate|constatari|istoric|diagnostic|recomandari|recomandare|examen)'
    r'(?=\s*(?:[:*]|$))[\s*_:.\u2013-]*', re.IGNORECASE)


def chunk_text(text: str) -> list[tuple]:
    """Text → [(section, passage)]: sentence groups of about _CHUNK_CHARS (hard
    cap _CHUNK_MAX), never crossing a paragraph break or a section header.
    `section` is the header in force at the start of the passage, as written
    ("Concluzii"), or None. Passages hold no blank lines, so joining them with
    "\n\n" can be split back."""
    out, section = [], None

    def flush(cur, sec):
        if cur:
            out.append((sec, cur))

    for para in re.split(r'\n\s*\n', text):
        cur, cur_sec = '', section
        for sent in _SENT_RE.split(para):
            sent = sent.strip()
            if not sent:
                continue
            m = _SECTION_RE.match(_fold(sent))
            if m:
                flush(cur, cur_sec)
                cur = ''
                section = re.match(r'^[\s*_#>-]*([^\s*_:.\u2013-]+)', sent).group(1)
                cur_sec = section
                sent = sent[m.end():].strip()
                if not sent:
                    continue
            while len(sent) > _CHUNK_MAX:      # a run-on sentence: cut at a space
                cut = sent.rfind(' ', 0, _CHUNK_MAX)
                if cut <= 0:
                    cut = _CHUNK_MAX
                flush(f'{cur} {sent[:cut]}'.strip() if cur else sent[:cut], cur_sec)
                cur, cur_sec, sent = '', section, sent[cut:].strip()
            if cur and len(cur) + len(sent) + 1 > _CHUNK_CHARS:
                flush(cur, cur_sec)
                cur, cur_sec = '', section
            cur = f'{cur} {sent}' if cur else sent
        flush(cur, cur_sec)
    return out


class SearchIndex:
    """SQLite-backed full-text index of epicrisis/imaging report text."""

    def __init__(self, db_path: str, max_age_days: int = 30):
        self.db_path = db_path
        self.max_age_days = max_age_days
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        con = self._connect()
        try:
            con.executescript(_SCHEMA)
            have = {r[1] for r in con.execute("PRAGMA table_info(documents)")}
            for col, typ in _META_COLUMNS.items():
                if col not in have:
                    con.execute(f"ALTER TABLE documents ADD COLUMN {col} {typ}")
            con.commit()
            self._build_missing_passages(con)
        finally:
            con.close()
        logger.info(f"SearchIndex initialised at {db_path}")

    @staticmethod
    def _write_passages(con: sqlite3.Connection, doc_id: int, text: str) -> None:
        """Replace a document's passages. Caller commits."""
        for (pid,) in con.execute("SELECT id FROM passages WHERE doc_id = ?", (doc_id,)).fetchall():
            con.execute("DELETE FROM passages_fts WHERE rowid = ?", (pid,))
        con.execute("DELETE FROM passages WHERE doc_id = ?", (doc_id,))
        for seq, (section, chunk) in enumerate(chunk_text(text)):
            pid = con.execute("INSERT INTO passages(doc_id, seq, section) VALUES (?, ?, ?) RETURNING id",
                              (doc_id, seq, section)).fetchone()[0]
            con.execute("INSERT INTO passages_fts(rowid, text) VALUES (?, ?)", (pid, chunk))

    def _build_missing_passages(self, con: sqlite3.Connection) -> None:
        """One-off, from the text already in documents_fts (no re-scrape):
        passages for documents indexed before the passage index existed."""
        rows = con.execute(
            """SELECT d.id, f.text FROM documents d JOIN documents_fts f ON f.rowid = d.id
               WHERE NOT EXISTS (SELECT 1 FROM passages p WHERE p.doc_id = d.id)""").fetchall()
        for n, (doc_id, text) in enumerate(rows, 1):
            self._write_passages(con, doc_id, text)
            if n % 500 == 0:
                con.commit()
        con.commit()
        if rows:
            logger.info(f"SearchIndex: built passages for {len(rows)} documents")

    def _connect(self) -> sqlite3.Connection:
        # Generous busy timeout: a long backfill batch and a live
        # schedule_index() write can briefly contend for the write lock.
        return sqlite3.connect(self.db_path, timeout=30)

    # ── blocking implementations (run off the event loop by the async wrappers) ──

    def _index_document_conn(self, con: sqlite3.Connection, kind: str, source_id: str,
                              cnp: Optional[str], name: Optional[str], text: str,
                              meta: Optional[dict] = None) -> None:
        """Upsert one document on an already-open connection. Caller commits.
        `meta`: optional doc_date / modality / title / status (see _META_COLUMNS)."""
        meta = meta or {}
        cur = con.execute(
            """INSERT INTO documents(kind, source_id, patient_cnp, patient_name, updated_at,
                                     doc_date, modality, title, status, identifiers)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(kind, source_id) DO UPDATE SET
                   patient_cnp=excluded.patient_cnp,
                   patient_name=excluded.patient_name,
                   updated_at=excluded.updated_at,
                   doc_date=excluded.doc_date,
                   modality=excluded.modality,
                   title=excluded.title,
                   status=excluded.status,
                   identifiers=excluded.identifiers
               RETURNING id""",
            (kind, source_id, cnp, name, time.time(),
             meta.get('doc_date'), meta.get('modality'), meta.get('title'), meta.get('status'),
             json.dumps(meta['identifiers'], ensure_ascii=False) if meta.get('identifiers') else None),
        )
        doc_id = cur.fetchone()[0]
        con.execute("DELETE FROM documents_fts WHERE rowid = ?", (doc_id,))
        con.execute("INSERT INTO documents_fts(rowid, text) VALUES (?, ?)", (doc_id, text))
        self._write_passages(con, doc_id, text)

    def _index_document_sync(self, kind: str, source_id: str,
                              cnp: Optional[str], name: Optional[str], text: str,
                              meta: Optional[dict] = None) -> None:
        con = self._connect()
        try:
            self._index_document_conn(con, kind, source_id, cnp, name, text, meta)
            con.commit()
        finally:
            con.close()

    def _search_sync(self, query: str, limit: int, snippet_length: int = 12) -> list[dict]:
        terms = _TOKEN_RE.findall(query)
        if not terms:
            return []
        # Quoted so a term like "and"/"or"/"not"/"near" is a literal prefix
        # match, not an FTS5 operator.
        match_query = ' '.join(f'"{t}"*' for t in terms)
        con = self._connect()
        try:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                """SELECT d.kind, d.source_id, d.patient_cnp, d.patient_name, d.updated_at,
                          snippet(documents_fts, 0, '<mark>', '</mark>', '…', ?) AS snippet
                   FROM documents_fts
                   JOIN documents d ON d.id = documents_fts.rowid
                   WHERE documents_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (snippet_length, match_query, limit * 20),
            ).fetchall()
            # What the caller wants is the patients having the keyword, not
            # every document that mentions it (the same history is copied into
            # each epicrisis, and one patient has many reports): one hit per
            # patient — the best-ranked document's snippet, with per-kind
            # document counts and the ids of all matching documents.
            hits: dict = {}
            for r in rows:
                r = dict(r)
                key = r['patient_cnp'] or r['patient_name']
                if key in hits:
                    h = hits[key]
                else:
                    h = hits[key] = {**r, 'count': 0, 'kinds': {}, 'documents': []}
                h['count'] += 1
                h['kinds'][r['kind']] = h['kinds'].get(r['kind'], 0) + 1
                h['documents'].append({'kind': r['kind'], 'source_id': r['source_id']})
            return list(hits.values())[:limit]
        finally:
            con.close()

    def _search_passages_sync(self, slots: list, match: str, min_match: int, kinds, modalities,
                              date_from, date_to, status: str, limit: int, max_chars: int,
                              context: int) -> list[dict]:
        if not slots:
            return []
        exprs = [_slot_fts(sl) for sl in slots]
        match_query = (' AND ' if match == 'all' else ' OR ').join(exprs)
        where, params = ["passages_fts MATCH ?"], [match_query]
        if status:
            where.append("d.status = ?"); params.append(status)
        if kinds:
            where.append(f"d.kind IN ({','.join('?' * len(kinds))})"); params += kinds
        if modalities:
            where.append(f"d.modality IN ({','.join('?' * len(modalities))})"); params += modalities
        if date_from:
            where.append("d.doc_date >= ?"); params.append(date_from)
        if date_to:
            where.append("d.doc_date <= ?"); params.append(date_to)
        con = self._connect()
        try:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                f"""SELECT d.id AS doc_id, d.kind, d.source_id, d.patient_cnp, d.patient_name,
                           d.doc_date, d.modality, d.title, d.status, d.identifiers,
                           p.seq, p.section, passages_fts.text AS text,
                           -bm25(passages_fts) AS bm25
                    FROM passages_fts
                    JOIN passages p ON p.id = passages_fts.rowid
                    JOIN documents d ON d.id = p.doc_id
                    WHERE {' AND '.join(where)}
                    ORDER BY bm25(passages_fts)
                    LIMIT ?""",
                params + [max(limit * 20, 300)]).fetchall()
            need = min_match if match == 'any' else len(slots)
            docs: dict = {}
            for r in rows:
                n = len(_slots_in(_fold(r['text']), slots))
                if n < need:
                    continue
                docs.setdefault(r['doc_id'], []).append((n, max(r['bm25'], 0.0), r))
            out = []
            for doc_id, hits in docs.items():
                hits.sort(key=lambda h: (-h[0], -h[1], h[2]['seq']))
                best_n, best_bm, first = hits[0]
                chosen, size = {}, 0
                for n, bm, r in hits:
                    if chosen and size + len(r['text']) + 2 > max_chars:
                        continue
                    chosen[r['seq']] = (r['section'], r['text'])
                    size += len(r['text']) + 2
                if context:
                    near = {j for q in list(chosen) for j in range(q - context, q + context + 1)} - set(chosen)
                    for seq, section, text in con.execute(
                            """SELECT p.seq, p.section, f.text FROM passages p
                               JOIN passages_fts f ON f.rowid = p.id
                               WHERE p.doc_id = ? AND p.seq BETWEEN ? AND ?""",
                            (doc_id, min(near, default=0), max(near, default=0))):
                        if seq in near and size + len(text) + 2 <= max_chars:
                            chosen[seq] = (section, text)
                            size += len(text) + 2
                passages = [{'section': chosen[q][0], 'text': chosen[q][1]} for q in sorted(chosen)]
                if len(passages) == 1 and len(passages[0]['text']) > max_chars:
                    passages[0]['text'] = passages[0]['text'][:max_chars].rsplit(' ', 1)[0] + '…'
                d = {k: first[k] for k in ('kind', 'source_id', 'patient_cnp', 'patient_name',
                                           'doc_date', 'modality', 'title', 'status')}
                d['identifiers'] = json.loads(first['identifiers']) if first['identifiers'] else {}
                d.update(passages=passages, passage='\n\n'.join(p['text'] for p in passages),
                         matched=best_n, score=round(best_n + best_bm / (1 + best_bm), 4))
                out.append(d)
        finally:
            con.close()
        out.sort(key=lambda d: d['score'], reverse=True)
        return out[:limit]

    def _stats_sync(self) -> dict:
        con = self._connect()
        try:
            def grp(col):
                return {k or '': n for k, n in con.execute(
                    f"SELECT {col}, count(*) FROM documents GROUP BY {col}")}
            lo, hi, last = con.execute(
                "SELECT min(doc_date), max(doc_date), max(updated_at) FROM documents").fetchone()
            return {'total': con.execute("SELECT count(*) FROM documents").fetchone()[0],
                    'passages': con.execute("SELECT count(*) FROM passages").fetchone()[0],
                    'by_kind': grp('kind'), 'by_modality': grp('modality'), 'by_status': grp('status'),
                    'date_min': lo, 'date_max': hi, 'last_indexed': last}
        finally:
            con.close()

    def _indexed_keys_sync(self) -> set:
        con = self._connect()
        try:
            # Rows without `status`/`identifiers` predate the metadata columns: leave them
            # out so the cache backfill re-parses (and thereby upgrades) them.
            return {(k, s) for k, s in con.execute(
                "SELECT kind, source_id FROM documents "
                "WHERE status IS NOT NULL AND identifiers IS NOT NULL")}
        finally:
            con.close()

    def _get_backfill_cursor_sync(self) -> float:
        con = self._connect()
        try:
            # One full rescan after the metadata columns were introduced.
            if not con.execute("SELECT 1 FROM meta WHERE key = 'meta_v2'").fetchone():
                return 0.0
            row = con.execute("SELECT value FROM meta WHERE key = 'backfill_cursor'").fetchone()
            return float(row[0]) if row else 0.0
        finally:
            con.close()

    def _set_backfill_cursor_sync(self, mtime: float) -> None:
        con = self._connect()
        try:
            con.execute(
                "INSERT INTO meta(key, value) VALUES ('backfill_cursor', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(mtime),))
            con.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('meta_v2', '1')")
            con.commit()
        finally:
            con.close()

    def _cleanup_sync(self, max_age_days: int) -> dict:
        if max_age_days <= 0:
            return {'deleted': 0}
        cutoff = time.time() - max_age_days * 86400
        con = self._connect()
        try:
            ids = [r[0] for r in con.execute(
                "SELECT id FROM documents WHERE updated_at < ?", (cutoff,)).fetchall()]
            for doc_id in ids:
                con.execute("DELETE FROM documents_fts WHERE rowid = ?", (doc_id,))
                for (pid,) in con.execute("SELECT id FROM passages WHERE doc_id = ?", (doc_id,)).fetchall():
                    con.execute("DELETE FROM passages_fts WHERE rowid = ?", (pid,))
                con.execute("DELETE FROM passages WHERE doc_id = ?", (doc_id,))
            con.execute("DELETE FROM documents WHERE updated_at < ?", (cutoff,))
            con.commit()
            return {'deleted': len(ids)}
        finally:
            con.close()

    # ── sync public API (for callers already running off the event loop in
    # their own background thread, e.g. the startup cache backfill below —
    # avoids an extra executor hop on top of the one they're already in) ──

    def index_document_sync(self, kind: str, source_id: str,
                             cnp: Optional[str], name: Optional[str], text: Optional[str],
                             meta: Optional[dict] = None) -> None:
        """Synchronous counterpart to index_document(). No-op if text is empty."""
        if not text or not text.strip():
            return
        self._index_document_sync(kind, source_id, cnp, name, text, meta)

    def indexed_keys_sync(self) -> set:
        """Synchronous counterpart to indexed_keys()."""
        return self._indexed_keys_sync()

    @contextmanager
    def batch_writer(self, commit_every: int = 100):
        """One connection/transaction for a whole batch of index_document_sync
        calls, instead of a fresh connection + commit per document.

        Meant for hippobridge.py's _backfill_search_sync, which can index
        hundreds of newly-cached documents in one pass — the live
        schedule_index()/index_document() fire-and-forget path (one document
        per scrape) still goes through the per-call connection, which is
        the right granularity there.

        Yields a callable with the same signature as index_document_sync().
        Commits every `commit_every` documents (so the write lock isn't held
        for the whole scan, starving live schedule_index() writes) and once
        more when the block exits, including on error — upserts are
        idempotent (ON CONFLICT DO UPDATE) and the backfill cursor is only
        advanced after the whole scan finishes, so losing an in-progress
        batch to a crash just means it's safely redone on the next run.
        """
        con = self._connect()
        pending = 0
        try:
            def _index(kind: str, source_id: str, cnp: Optional[str], name: Optional[str],
                        text: Optional[str], meta: Optional[dict] = None) -> None:
                nonlocal pending
                if not text or not text.strip():
                    return
                self._index_document_conn(con, kind, source_id, cnp, name, text, meta)
                pending += 1
                if pending >= commit_every:
                    con.commit()
                    pending = 0
            yield _index
        finally:
            con.commit()
            con.close()

    def get_backfill_cursor_sync(self) -> float:
        """Newest cache-file mtime processed by the last cache backfill scan
        (see hippobridge.py's _backfill_search_sync), 0.0 if never run.
        Lets a repeat scan walk only files written since then instead of the
        whole disk cache — see urlcache.FilesystemCache.iter_entries()."""
        return self._get_backfill_cursor_sync()

    def set_backfill_cursor_sync(self, mtime: float) -> None:
        """Persist the backfill cursor (see get_backfill_cursor_sync)."""
        self._set_backfill_cursor_sync(mtime)

    # ── async public API ──

    async def index_document(self, kind: str, source_id: str,
                              cnp: Optional[str], name: Optional[str], text: str,
                              meta: Optional[dict] = None) -> None:
        """Upsert a document's searchable text. No-op if text is empty."""
        if not text or not text.strip():
            return
        await asyncio.get_event_loop().run_in_executor(
            None, self._index_document_sync, kind, source_id, cnp, name, text, meta)

    async def indexed_keys(self) -> set:
        """Return the set of (kind, source_id) pairs already indexed."""
        return await asyncio.get_event_loop().run_in_executor(None, self._indexed_keys_sync)

    async def search(self, query: str, limit: int = 25, snippet_length: int = 12) -> list[dict]:
        """Return up to `limit` matching documents, ranked by FTS5 relevance.
        `snippet_length` is the snippet size in tokens, clamped to FTS5's 1–64."""
        snippet_length = max(1, min(64, snippet_length))
        return await asyncio.get_event_loop().run_in_executor(
            None, self._search_sync, query, limit, snippet_length)

    async def search_passages(self, query: str, match: str = 'all', min_match: int = 1,
                              kinds=None, modalities=None, date_from: Optional[str] = None,
                              date_to: Optional[str] = None, status: str = 'final',
                              limit: int = 30, max_chars: int = 900, context: int = 0) -> list[dict]:
        """One result per document, best first, each with its best passage(s)
        (`passage`, at most ~`max_chars`), `score` and `matched` (query words
        found in the document). `query` words are prefix-matched; "quoted
        phrases" and `a|b` alternatives count as one word each. match='any'
        needs `min_match` of the words, 'all' every one."""
        slots = parse_query(query)
        return await asyncio.get_event_loop().run_in_executor(
            None, self._search_passages_sync, slots, match, max(1, min_match), kinds or [],
            modalities or [], date_from, date_to, status, limit, max_chars, context)

    async def stats(self) -> dict:
        """Counts per kind/modality/status, date range and last write."""
        return await asyncio.get_event_loop().run_in_executor(None, self._stats_sync)

    async def cleanup(self, max_age_days: Optional[int] = None) -> dict:
        """Evict documents older than max_age_days (default: self.max_age_days).

        Mirrors urlcache.FilesystemCache.cleanup()'s signature/semantics.
        """
        if max_age_days is None:
            max_age_days = self.max_age_days
        return await asyncio.get_event_loop().run_in_executor(
            None, self._cleanup_sync, max_age_days)


# Set by hippobridge.init_app() when [cache] dir is configured; stays None
# (feature silently disabled) otherwise. Mirrors hippoclient.py's
# `url_cache = URLCache()` / `ai_cache` module-singleton pattern.
instance: Optional[SearchIndex] = None

# Keeps fire-and-forget index tasks alive — asyncio.Task only holds a weak
# reference once nothing else references it, so an unreferenced task can be
# garbage-collected mid-write. Discarded via add_done_callback once finished.
_pending_tasks: set = set()


def schedule_index(kind: str, source_id: str, cnp: Optional[str], name: Optional[str],
                    text: Optional[str], meta: Optional[dict] = None) -> None:
    """Fire-and-forget index a document into `instance`, if configured.

    Called from hippoclient.py's HippoClientCheckout/HippoClientImagingStudy
    fetch_and_parse() overrides. Indexing must never slow down or break the
    actual scrape response, so this only schedules a background task and
    swallows/logs its own failures.
    """
    if instance is None or not text:
        return

    async def _run():
        try:
            await instance.index_document(kind, source_id, cnp, name, text, meta)
        except Exception as exc:
            logger.warning(f"Search index update failed ({kind} {source_id}): {exc}")

    task = asyncio.get_event_loop().create_task(_run())
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)
