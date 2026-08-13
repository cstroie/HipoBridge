#!/usr/bin/env python3
"""URL cache implementation for HTTP response caching with LRU eviction and timeout.

This module provides a two-tier cache for HTTP responses:

  L1 — URLCache: in-memory LRU with short TTL (default 30 min) and asyncio
       stampede prevention.  Fast, but lost on restart.

  L2 — a persistent backing store, attached via the ``fs_cache`` attribute
       (see sqlcache.py's SqliteCache).  Survives restarts; optional
       (disabled when no cache directory is configured).  Duck-typed:
       anything exposing get(url)/put(url, text)/remove(url) can be
       attached, decoupling URLCache from any specific L2 implementation.

When L2 is attached to URLCache, a cache miss in L1 is followed by an L2 lookup.
A hit in L2 warms L1 so subsequent requests stay in memory.  Both tiers are
invalidated together on explicit eviction.
"""

import asyncio
from collections import OrderedDict
import copy
from datetime import datetime, timezone
import logging
from typing import Any, Optional

logger = logging.getLogger('URLCache')


class URLCache:
    """In-memory LRU cache for HTTP responses with TTL expiry and stampede prevention.

    Stores HTTP response text keyed by URL. When a URL is being fetched by one
    coroutine, subsequent requests for the same URL wait for the in-flight result
    rather than issuing redundant upstream requests.

    If a duck-typed L2 backing store is attached (via the fs_cache attribute,
    see sqlcache.py's SqliteCache), it's used as an L2 backing store: misses
    in L1 fall through to L2, and writes to L1 are optionally mirrored to L2
    (controlled by the persist= parameter on put()).

    Thread/coroutine safety: designed for asyncio (single-threaded event loop).
    is_inflight() and mark_inflight() must be called without an intervening
    ``await`` to remain effectively atomic.
    """

    def __init__(self, max_size: int = 500, timeout: int = 1800):
        """
        Args:
            max_size: Maximum number of cached entries (default: 500).
            timeout:  TTL in seconds (default: 1800 / 30 min).
        """
        self.max_size = max_size
        self.timeout = timeout
        # OrderedDict maps url → (response_text, utc_timestamp)
        # Insertion/access order reflects LRU: oldest entry is first.
        self._cache: OrderedDict[str, tuple[str, datetime]] = OrderedDict()
        # url → asyncio.Event set when the fetch completes
        self._inflight: dict[str, asyncio.Event] = {}
        # Optional L2 backing store (duck-typed get/put/remove); set by init_app() after construction
        self.fs_cache: Optional[Any] = None

    def _l1_get(self, url: str) -> Optional[str]:
        """Check L1 only; returns None on miss or expiry (does not touch L2)."""
        if url in self._cache:
            text, ts = self._cache[url]
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            if age >= self.timeout:
                del self._cache[url]
                self._inflight.pop(url, None)
                logger.debug(f"Expired cache entry removed: {url}")
            else:
                self._cache.move_to_end(url)
                logger.debug(f"Cache hit (L1): {url} (age {age:.1f}s)")
                return text
        return None

    def get(self, url: str) -> Optional[str]:
        """Return cached response for url, or None if absent or expired.

        Checks L1 first.  On L1 miss, checks L2 (filesystem) if attached; a
        hit there warms L1 so the next request stays in memory.

        Synchronous — does blocking disk I/O on L2 miss/hit. Prefer
        ``get_async`` from coroutines so filesystem access doesn't stall the
        event loop; this sync version remains for non-async callers.
        """
        text = self._l1_get(url)
        if text is not None:
            return text

        if self.fs_cache is not None:
            text = self.fs_cache.get(url)
            if text is not None:
                # Warm L1 without writing back to L2
                self._l1_put(url, text)
                return text

        return None

    async def get_async(self, url: str) -> Optional[str]:
        """Async equivalent of ``get`` — runs L2 filesystem I/O in a thread
        so it doesn't block the event loop."""
        text = self._l1_get(url)
        if text is not None:
            return text

        if self.fs_cache is not None:
            text = await asyncio.to_thread(self.fs_cache.get, url)
            if text is not None:
                self._l1_put(url, text)
                return text

        return None

    def _l1_put(self, url: str, response_text: str) -> None:
        """Insert or refresh L1 only (no L2 write)."""
        if url in self._cache:
            self._cache[url] = (response_text, datetime.now(timezone.utc))
            self._cache.move_to_end(url)
        else:
            if len(self._cache) >= self.max_size:
                oldest_url, _ = self._cache.popitem(last=False)
                logger.debug(f"Evicted LRU cache entry: {oldest_url}")
            self._cache[url] = (response_text, datetime.now(timezone.utc))

    def _l1_put_entry(self, url: str, response_text: str) -> None:
        """Insert or refresh L1 (shared by put/put_async)."""
        if url in self._cache:
            self._cache[url] = (response_text, datetime.now(timezone.utc))
            self._cache.move_to_end(url)
            logger.debug(f"Refreshed cache entry: {url}")
        else:
            if len(self._cache) >= self.max_size:
                oldest_url, _ = self._cache.popitem(last=False)
                logger.debug(f"Evicted LRU cache entry: {oldest_url}")
            self._cache[url] = (response_text, datetime.now(timezone.utc))
            logger.debug(f"Cached response: {url}")

    def put(self, url: str, response_text: str, persist: bool = True) -> None:
        """Insert or refresh a cache entry, evicting the LRU entry if at capacity.

        Args:
            url:           URL key.
            response_text: Response body to cache.
            persist:       If True and an L2 FilesystemCache is attached, also
                           write to L2.  Pass False for user-specific or highly
                           volatile pages that must not persist across restarts.

        Synchronous — does blocking disk I/O when persisting to L2. Prefer
        ``put_async`` from coroutines so filesystem access doesn't stall the
        event loop; this sync version remains for non-async callers.
        """
        self._l1_put_entry(url, response_text)
        if persist and self.fs_cache is not None:
            self.fs_cache.put(url, response_text)

    async def put_async(self, url: str, response_text: str, persist: bool = True) -> None:
        """Async equivalent of ``put`` — runs L2 filesystem I/O in a thread
        so it doesn't block the event loop."""
        self._l1_put_entry(url, response_text)
        if persist and self.fs_cache is not None:
            await asyncio.to_thread(self.fs_cache.put, url, response_text)

    def remove(self, url: str) -> None:
        """Remove a specific cache entry from both L1 and L2.

        Does not cancel an in-flight fetch for the same URL — the fetcher's
        ``resolve_inflight`` call will still wake up any waiters. If the fetch
        completes after removal, ``put`` will re-insert the entry; callers that
        need permanent eviction (e.g. empty-result suppression) should call
        ``remove`` only after the fetch has completed and ``resolve_inflight``
        has already been called.

        Synchronous — does blocking disk I/O when an L2 cache is attached.
        Prefer ``remove_async`` from coroutines.
        """
        if url:
            self._cache.pop(url, None)
            if self.fs_cache is not None:
                self.fs_cache.remove(url)

    async def remove_async(self, url: str) -> None:
        """Async equivalent of ``remove`` — runs L2 filesystem I/O in a thread
        so it doesn't block the event loop."""
        if url:
            self._cache.pop(url, None)
            if self.fs_cache is not None:
                await asyncio.to_thread(self.fs_cache.remove, url)

    def clear(self) -> None:
        """Clear all cache entries and resolve any pending in-flight events."""
        self._cache.clear()
        for event in self._inflight.values():
            event.set()
        self._inflight.clear()

    # ------------------------------------------------------------------
    # In-flight deduplication
    # ------------------------------------------------------------------

    def is_inflight(self, url: str) -> bool:
        """Return True if a fetch for this URL is already in progress."""
        return url in self._inflight

    def mark_inflight(self, url: str) -> asyncio.Event:
        """Register url as being fetched.

        If an event already exists (two coroutines raced through is_inflight
        without an await between them — impossible in asyncio but guarded
        defensively), the existing event is returned so both callers share it.
        """
        if url not in self._inflight:
            self._inflight[url] = asyncio.Event()
        return self._inflight[url]

    def resolve_inflight(self, url: str) -> None:
        """Mark the in-flight fetch as complete and wake up any waiters."""
        event = self._inflight.pop(url, None)
        if event:
            event.set()

    async def wait_inflight(self, url: str) -> None:
        """Wait until the in-flight fetch for url completes (or is abandoned).

        If the event was already resolved before this call returns, ``await``
        returns immediately because ``asyncio.Event.wait()`` returns at once
        when the flag is already set.
        """
        event = self._inflight.get(url)
        if event:
            await event.wait()


class ParseResultCache:
    """In-memory cache for *parsed* page results, layered on top of URLCache.

    A page fetched through URLCache still gets re-parsed (BeautifulSoup, regex
    extraction, etc.) on every call even when the raw HTML was itself a cache
    hit. This cache short-circuits that: keyed by (url, parser_class_name), it
    skips parse_data() entirely when both the page and the parse of it are
    still fresh.

    Why (url, class_name) is a safe key: every HippoClient parse_data()
    implementation only reads kwargs that are already embedded in the URL
    used to fetch the page (id, lab_id, etc. are template placeholders
    substituted by _format_request_url()/_build_url() before the request is
    made) — so for a fixed url, parse_data's output depends only on which
    parser class is doing the parsing, never on anything else. Two different
    classes can legitimately parse the same url differently, hence class_name
    is part of the key.

    L1-only, deliberately: this cache exists purely to skip redundant CPU
    work (parsing), not to reduce load on Hipocrate — that's the raw-page
    URLCache/SqliteCache's job (see module docstring). No persistence
    across restarts is needed or attempted.

    HippoData is a mutable dict subclass, and callers routinely mutate a
    parse result after receiving it (.store()/.store_list() to add derived
    fields, apply filters, etc.) — so both get() and put() deep-copy: put()
    stores an isolated copy so a caller mutating the object it just parsed
    can't corrupt the cached entry, and get() returns a fresh copy so each
    hit can be mutated independently without affecting the next hit.

    Entries are nested by url first so invalidating a url (raw page changed
    or was evicted) drops every parser's cached result for it in one dict
    delete, regardless of which classes had parsed it.
    """

    def __init__(self, max_size: int = 300, timeout: int = 1800):
        self.max_size = max_size
        self.timeout = timeout
        # url -> {class_name: (deepcopy_of_result, utc_timestamp)}
        self._cache: OrderedDict[str, dict] = OrderedDict()

    def get(self, url: str, class_name: str) -> Optional[Any]:
        entry = self._cache.get(url)
        if entry is None:
            return None
        hit = entry.get(class_name)
        if hit is None:
            return None
        value, ts = hit
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        if age >= self.timeout:
            del entry[class_name]
            if not entry:
                del self._cache[url]
            return None
        self._cache.move_to_end(url)
        logger.debug(f"Parse cache hit: {class_name} / {url} (age {age:.1f}s)")
        return copy.deepcopy(value)

    def put(self, url: str, class_name: str, value: Any) -> None:
        if url not in self._cache:
            if len(self._cache) >= self.max_size:
                evicted_url, _ = self._cache.popitem(last=False)
                logger.debug(f"Evicted LRU parse cache entry: {evicted_url}")
            self._cache[url] = {}
        self._cache[url][class_name] = (copy.deepcopy(value), datetime.now(timezone.utc))
        self._cache.move_to_end(url)
        logger.debug(f"Parse cache stored: {class_name} / {url}")

    def evict(self, url: str) -> None:
        """Drop every parser's cached result for this url (raw page changed/evicted)."""
        self._cache.pop(url, None)

    def clear(self) -> None:
        self._cache.clear()
