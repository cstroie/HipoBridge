#!/usr/bin/env python3
"""SQLite-backed L2 cache for HTTP response text.

Replaces the previous JSON-file-per-key FilesystemCache with a single
`cache.db` SQLite database holding one table per scraped-page "kind" (raw
HTML from Hipocrate: patient, checkin, checkout, epicrisis, imaging, lab
results, ...) plus a dedicated `cache_ai` table for AI-generated content.
Each raw-HTML table carries the full `url` (primary key, exactly like the
old MD5(url) keying) alongside a natural `record_key` (patient code, request
id, ...) so per-entity queries and `stats()` breakdowns don't require
parsing the URL again.

Connection lifecycle: unlike search.py's per-call connect/close (fine
for its occasional document upserts), this cache is write-heavy — every L2
miss on a live scrape writes an entry — so a single persistent connection in
WAL mode is kept open for the process lifetime. WAL mode creates
`cache.db-wal`/`cache.db-shm` sidecar files next to `cache.db`; that's
expected, not corruption. sqlite3 connections aren't safe for concurrent use
by multiple threads, and callers reach this module via `asyncio.to_thread`
(no fixed worker thread), so every method holds `self._lock` for its
execute/commit, reads included.

`get`/`put`/`remove` resolve which table a URL belongs to via `route()`
below — a single declarative mapping, kept independent of which HippoClient
subclass is calling, since cache_get/cache_put (hippoclient.py) only ever
see a bare URL by the time they're invoked.
"""

import logging
import re
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Callable, Optional, Union
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger('SqliteCache')

# ---------------------------------------------------------------------------
# URL -> (table, record_key) routing
# ---------------------------------------------------------------------------

_FALLBACK_TABLE = 'cache_other'


def _episode_key(query: dict) -> Optional[str]:
    pacid = query.get('pacid', [None])[0]
    domain = query.get('strDomeniu', [None])[0]
    year = query.get('strAN', [None])[0]
    return f"{pacid}:{domain or 'all'}:{year or ''}"


def _buletin_table(query: dict) -> str:
    if query.get('type', [None])[0] == '3':
        return 'cache_imaging_buletin'
    return 'cache_report_buletin'


_ROUTES: list[tuple['re.Pattern[str]', Union[str, Callable[[dict], str]], Callable[[dict], Optional[str]]]] = [
    (re.compile(r'/Pacient/edit\.asp'), 'cache_patient', lambda q: q.get('id', [None])[0]),
    (re.compile(r'/Pacient/analysesEpisod\.asp'), 'cache_episode', _episode_key),
    (re.compile(r'/gen_printabile/BiletExternare\.asp'), 'cache_checkout', lambda q: q.get('RelId', [None])[0]),
    (re.compile(r'/files/checkin\.asp'), 'cache_checkin', lambda q: q.get('id', [None])[0]),
    (re.compile(r'/files/checkup\.asp'), 'cache_checkup', lambda q: q.get('cuid', [None])[0]),
    (re.compile(r'/PARA/NOM/Listare/cerere\.asp'), 'cache_cerere', lambda q: q.get('id', [None])[0]),
    (re.compile(r'/gen_printabile/FisaPrezentare\.asp'), 'cache_presentation', lambda q: q.get('id', [None])[0]),
    (re.compile(r'/PARA/Printabile/BuletinAnalize\.asp'), _buletin_table, lambda q: q.get('id', [None])[0]),
    (re.compile(r'/PARA/Printabile/buletinRecoltari\.asp'), 'cache_report_buletin', lambda q: q.get('id', [None])[0]),
    (re.compile(r'/PARA/Printabile/BuletinSolicitare\.asp'), 'cache_solicitare', lambda q: q.get('id', [None])[0]),
]

# Every raw-HTML table this module knows about, including the fallback —
# used by cleanup()/iter_entries()/stats() to iterate "all tables".
RAW_HTML_TABLES = [
    'cache_patient', 'cache_episode', 'cache_checkout', 'cache_checkin',
    'cache_checkup', 'cache_cerere', 'cache_presentation',
    'cache_report_buletin', 'cache_imaging_buletin', 'cache_solicitare',
    _FALLBACK_TABLE,
]


def route(url: str) -> tuple[str, Optional[str]]:
    """Return (table_name, record_key) for a URL.

    Falls back to cache_other if nothing matches, so an unrecognized future
    URL still gets an L2 slot instead of silently losing disk caching. Not
    logged here: GET/remove reach every URL touched by the app regardless of
    whether it's ever actually persisted (L1-only URLs like whoami still hit
    an L2 get() on every L1 miss), so a warning here would fire constantly
    for URLs that are deliberately never written to L2 at all
    (_NO_PERSIST_PATTERNS in hippoclient.py). put() below logs instead,
    since a write landing in cache_other is the actionable signal that a new
    named table is worth adding.
    """
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for pattern, table_or_fn, key_fn in _ROUTES:
        if pattern.search(parsed.path):
            table = table_or_fn(query) if callable(table_or_fn) else table_or_fn
            try:
                return table, key_fn(query)
            except (KeyError, IndexError):
                return _FALLBACK_TABLE, None
    return _FALLBACK_TABLE, None


class SqliteCache:
    """SQLite-backed L2 cache: one table per raw-HTML kind, plus cache_ai."""

    def __init__(self, db_path: str, ttl: int = 7 * 86400, max_age_days: int = 30):
        """
        Args:
            db_path:      Path to the sqlite database file. Created on first use.
            ttl:          Time-to-live in seconds for raw-HTML entries (default: 7 days).
            max_age_days: Hard upper bound on entry age for cleanup(); entries
                          older than this are deleted even if not yet expired.
                          0 = no hard limit (default: 30).
        """
        self.db_path = db_path
        self.ttl = ttl
        self.max_age_days = max_age_days
        self._lock = threading.Lock()
        self._con = sqlite3.connect(db_path, check_same_thread=False)
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()
        logger.info(f"SqliteCache initialised at {db_path} (TTL {ttl}s, max_age {max_age_days}d)")

    def _init_schema(self) -> None:
        with self._lock:
            for table in RAW_HTML_TABLES:
                self._con.execute(f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        url         TEXT PRIMARY KEY,
                        record_key  TEXT,
                        content     TEXT NOT NULL,
                        cached_at   REAL NOT NULL,
                        expires_at  REAL NOT NULL
                    )
                """)
                self._con.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{table}_record_key ON {table}(record_key)")
                self._con.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{table}_cached_at ON {table}(cached_at)")
            self._con.execute("""
                CREATE TABLE IF NOT EXISTS cache_ai (
                    cache_key   TEXT PRIMARY KEY,
                    kind        TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    cached_at   REAL NOT NULL,
                    expires_at  REAL NOT NULL
                )
            """)
            self._con.execute("CREATE INDEX IF NOT EXISTS idx_cache_ai_kind ON cache_ai(kind)")
            self._con.execute("CREATE INDEX IF NOT EXISTS idx_cache_ai_cached_at ON cache_ai(cached_at)")
            self._con.commit()

    @staticmethod
    def _now() -> float:
        return datetime.now(timezone.utc).timestamp()

    # ------------------------------------------------------------------
    # Raw-HTML cache (routed by URL)
    # ------------------------------------------------------------------

    def get(self, url: str) -> Optional[str]:
        """Return cached content for url, or None if absent or expired."""
        table, _ = route(url)
        now = self._now()
        with self._lock:
            row = self._con.execute(
                f"SELECT content, expires_at FROM {table} WHERE url = ?", (url,)).fetchone()
            if row is None:
                return None
            content, expires_at = row
            if expires_at < now:
                self._con.execute(f"DELETE FROM {table} WHERE url = ?", (url,))
                self._con.commit()
                logger.debug(f"Cache expired: {url}")
                return None
            logger.debug(f"Cache hit: {url}")
            return content

    def put(self, url: str, text: str) -> None:
        """Write url -> text to the cache."""
        table, record_key = route(url)
        if table == _FALLBACK_TABLE:
            logger.warning(f"Persisting to fallback table {_FALLBACK_TABLE}, no named route for {url}")
        now = self._now()
        with self._lock:
            self._con.execute(
                f"""INSERT INTO {table} (url, record_key, content, cached_at, expires_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        record_key=excluded.record_key,
                        content=excluded.content,
                        cached_at=excluded.cached_at,
                        expires_at=excluded.expires_at""",
                (url, record_key, text, now, now + self.ttl))
            self._con.commit()
            logger.debug(f"Cache stored: {url}")

    def remove(self, url: str) -> None:
        """Delete the cache entry for url (no-op if absent)."""
        table, _ = route(url)
        with self._lock:
            self._con.execute(f"DELETE FROM {table} WHERE url = ?", (url,))
            self._con.commit()

    def cleanup(self, max_age_days: Optional[int] = None) -> dict:
        """Delete expired (and optionally aged-out) cache entries.

        Returns:
            dict with keys 'deleted' (count) and 'freed_bytes' (approx).
        """
        if max_age_days is None:
            max_age_days = self.max_age_days
        now = self._now()
        hard_cutoff = (now - max_age_days * 86400) if max_age_days else None
        deleted = 0
        freed = 0
        with self._lock:
            for table in RAW_HTML_TABLES:
                if hard_cutoff is not None:
                    rows = self._con.execute(
                        f"SELECT url, LENGTH(content) FROM {table} WHERE expires_at < ? OR cached_at < ?",
                        (now, hard_cutoff)).fetchall()
                else:
                    rows = self._con.execute(
                        f"SELECT url, LENGTH(content) FROM {table} WHERE expires_at < ?", (now,)).fetchall()
                if rows:
                    self._con.executemany(
                        f"DELETE FROM {table} WHERE url = ?", [(r[0],) for r in rows])
                    deleted += len(rows)
                    freed += sum(r[1] for r in rows)
            self._con.commit()
        logger.info(f"Cache cleanup: deleted {deleted} entries ({freed} bytes)")
        return {'deleted': deleted, 'freed_bytes': freed}

    def iter_entries(self, since_mtime: float = 0.0):
        """Yield (url, content, cached_at) for every non-expired raw-HTML
        entry written since since_mtime (default 0.0 — everything).

        Excludes cache_ai. Used by hippobridge.py's periodic search-index
        backfill; since_mtime is a persisted cursor compared with '>'
        against cached_at, so this must keep yielding raw unix timestamps.
        """
        now = self._now()
        with self._lock:
            for table in RAW_HTML_TABLES:
                rows = self._con.execute(
                    f"""SELECT url, content, cached_at FROM {table}
                        WHERE cached_at > ? AND expires_at >= ?""",
                    (since_mtime, now)).fetchall()
                for url, content, cached_at in rows:
                    if url and content:
                        yield url, content, cached_at

    def stats(self) -> dict:
        """Return aggregate statistics about the cache."""
        entries = 0
        size_bytes = 0
        expired = 0
        oldest: Optional[float] = None
        newest: Optional[float] = None
        by_table: dict = {}
        now = self._now()
        with self._lock:
            for table in RAW_HTML_TABLES:
                count, size, exp_count, tmin, tmax = self._con.execute(
                    f"""SELECT COUNT(*), COALESCE(SUM(LENGTH(content)), 0),
                               SUM(CASE WHEN expires_at < ? THEN 1 ELSE 0 END),
                               MIN(cached_at), MAX(cached_at)
                        FROM {table}""",
                    (now,)).fetchone()
                by_table[table] = count
                entries += count
                size_bytes += size
                expired += exp_count or 0
                if tmin is not None and (oldest is None or tmin < oldest):
                    oldest = tmin
                if tmax is not None and (newest is None or tmax > newest):
                    newest = tmax
        return {
            'entries': entries,
            'expired': expired,
            'size_bytes': size_bytes,
            'oldest': datetime.fromtimestamp(oldest, tz=timezone.utc).isoformat() if oldest else None,
            'newest': datetime.fromtimestamp(newest, tz=timezone.utc).isoformat() if newest else None,
            'cache_dir': self.db_path,
            'ttl_seconds': self.ttl,
            'by_table': by_table,
        }

    # ------------------------------------------------------------------
    # AI-content cache (keyed by "{kind}:{sha256(text)}", not URL-routed)
    # ------------------------------------------------------------------

    def get_ai(self, cache_key: str) -> Optional[str]:
        now = self._now()
        with self._lock:
            row = self._con.execute(
                "SELECT content, expires_at FROM cache_ai WHERE cache_key = ?", (cache_key,)).fetchone()
            if row is None:
                return None
            content, expires_at = row
            if expires_at < now:
                self._con.execute("DELETE FROM cache_ai WHERE cache_key = ?", (cache_key,))
                self._con.commit()
                return None
            return content

    def put_ai(self, cache_key: str, kind: str, text: str, ttl: int) -> None:
        now = self._now()
        with self._lock:
            self._con.execute(
                """INSERT INTO cache_ai (cache_key, kind, content, cached_at, expires_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(cache_key) DO UPDATE SET
                       kind=excluded.kind,
                       content=excluded.content,
                       cached_at=excluded.cached_at,
                       expires_at=excluded.expires_at""",
                (cache_key, kind, text, now, now + ttl))
            self._con.commit()

    def remove_ai(self, cache_key: str) -> None:
        with self._lock:
            self._con.execute("DELETE FROM cache_ai WHERE cache_key = ?", (cache_key,))
            self._con.commit()


class AiCacheView:
    """Adapter exposing FilesystemCache's get/put/remove surface, backed by
    SqliteCache's cache_ai table, so it can be assigned to URLCache.fs_cache
    (ai_cache) without URLCache itself needing to know about AI vs raw-HTML
    routing. `url` here is actually ai_cache's "{kind}:{sha256}" cache key,
    kept as `url` for signature parity with the duck-typed contract.
    """

    def __init__(self, cache: SqliteCache, ttl: int):
        self._cache = cache
        self.ttl = ttl

    def get(self, url: str) -> Optional[str]:
        return self._cache.get_ai(url)

    def put(self, url: str, text: str) -> None:
        kind = url.split(':', 1)[0] if ':' in url else url
        self._cache.put_ai(url, kind, text, self.ttl)

    def remove(self, url: str) -> None:
        self._cache.remove_ai(url)
