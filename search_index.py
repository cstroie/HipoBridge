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
hippobridge.py just sets `search_index.instance` in init_app() and reads it
back for the /api/search/text route and periodic cleanup.

SQLite FTS5, tokenized with unicode61 remove_diacritics 2 so a search for
"cauza" also matches "cauzâ"/"cauză" as typed inconsistently in Romanian
clinical text. All blocking sqlite3 calls run via run_in_executor, mirroring
how urlcache.FilesystemCache is already kept off the event loop.
"""

import asyncio
import logging
import re
import sqlite3
import time
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
"""

# FTS5 query-syntax characters that would otherwise be interpreted as
# operators (", *, -, (, ) etc.) rather than literal search text.
_TOKEN_RE = re.compile(r'[\w]+', re.UNICODE)


class SearchIndex:
    """SQLite-backed full-text index of epicrisis/imaging report text."""

    def __init__(self, db_path: str, max_age_days: int = 30):
        self.db_path = db_path
        self.max_age_days = max_age_days
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        con = self._connect()
        try:
            con.executescript(_SCHEMA)
            con.commit()
        finally:
            con.close()
        logger.info(f"SearchIndex initialised at {db_path}")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    # ── blocking implementations (run off the event loop by the async wrappers) ──

    def _index_document_sync(self, kind: str, source_id: str,
                              cnp: Optional[str], name: Optional[str], text: str) -> None:
        con = self._connect()
        try:
            cur = con.execute(
                """INSERT INTO documents(kind, source_id, patient_cnp, patient_name, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(kind, source_id) DO UPDATE SET
                       patient_cnp=excluded.patient_cnp,
                       patient_name=excluded.patient_name,
                       updated_at=excluded.updated_at
                   RETURNING id""",
                (kind, source_id, cnp, name, time.time()),
            )
            doc_id = cur.fetchone()[0]
            con.execute("DELETE FROM documents_fts WHERE rowid = ?", (doc_id,))
            con.execute("INSERT INTO documents_fts(rowid, text) VALUES (?, ?)", (doc_id, text))
            con.commit()
        finally:
            con.close()

    def _search_sync(self, query: str, limit: int) -> list[dict]:
        terms = _TOKEN_RE.findall(query)
        if not terms:
            return []
        match_query = ' '.join(f'{t}*' for t in terms)
        con = self._connect()
        try:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                """SELECT d.kind, d.source_id, d.patient_cnp, d.patient_name, d.updated_at,
                          snippet(documents_fts, 0, '<mark>', '</mark>', '…', 12) AS snippet
                   FROM documents_fts
                   JOIN documents d ON d.id = documents_fts.rowid
                   WHERE documents_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (match_query, limit),
            ).fetchall()
            return [dict(r) for r in rows]
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
            con.execute("DELETE FROM documents WHERE updated_at < ?", (cutoff,))
            con.commit()
            return {'deleted': len(ids)}
        finally:
            con.close()

    # ── async public API ──

    async def index_document(self, kind: str, source_id: str,
                              cnp: Optional[str], name: Optional[str], text: str) -> None:
        """Upsert a document's searchable text. No-op if text is empty."""
        if not text or not text.strip():
            return
        await asyncio.get_event_loop().run_in_executor(
            None, self._index_document_sync, kind, source_id, cnp, name, text)

    async def search(self, query: str, limit: int = 25) -> list[dict]:
        """Return up to `limit` matching documents, ranked by FTS5 relevance."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._search_sync, query, limit)

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
                    text: Optional[str]) -> None:
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
            await instance.index_document(kind, source_id, cnp, name, text)
        except Exception as exc:
            logger.warning(f"Search index update failed ({kind} {source_id}): {exc}")

    task = asyncio.get_event_loop().create_task(_run())
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)
