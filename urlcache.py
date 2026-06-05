#!/usr/bin/env python3
"""URL cache implementation for HTTP response caching with LRU eviction and timeout.

This module provides a simple in-memory cache for HTTP responses with automatic
expiration based on configurable timeout periods. It implements a Least Recently
Used (LRU) cache for storing HTTP response content, with in-flight request
deduplication to prevent cache stampedes under concurrent load.
"""

import asyncio
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional
import logging

logger = logging.getLogger('URLCache')


class URLCache:
    """In-memory LRU cache for HTTP responses with TTL expiry and stampede prevention.

    Stores HTTP response text keyed by URL. When a URL is being fetched by one
    coroutine, subsequent requests for the same URL wait for the in-flight result
    rather than issuing redundant upstream requests.

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

    def get(self, url: str) -> Optional[str]:
        """Return cached response for url, or None if absent or expired."""
        if url not in self._cache:
            return None

        text, ts = self._cache[url]
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        if age >= self.timeout:
            del self._cache[url]
            # Clean up any stale inflight entry for the same URL
            self._inflight.pop(url, None)
            logger.debug(f"Expired cache entry removed: {url}")
            return None

        # Move to end → most-recently-used position
        self._cache.move_to_end(url)
        logger.debug(f"Cache hit: {url} (age {age:.1f}s)")
        return text

    def put(self, url: str, response_text: str) -> None:
        """Insert or refresh a cache entry, evicting the LRU entry if at capacity."""
        if url in self._cache:
            # Refresh value and promote to MRU position
            self._cache[url] = (response_text, datetime.now(timezone.utc))
            self._cache.move_to_end(url)
            logger.debug(f"Refreshed cache entry: {url}")
            return

        if len(self._cache) >= self.max_size:
            oldest_url, _ = self._cache.popitem(last=False)
            logger.debug(f"Evicted LRU cache entry: {oldest_url}")

        self._cache[url] = (response_text, datetime.now(timezone.utc))
        logger.debug(f"Cached response: {url}")

    def remove(self, url: str) -> None:
        """Remove a specific cache entry.

        Does not cancel an in-flight fetch for the same URL — the fetcher's
        ``resolve_inflight`` call will still wake up any waiters. If the fetch
        completes after removal, ``put`` will re-insert the entry; callers that
        need permanent eviction (e.g. empty-result suppression) should call
        ``remove`` only after the fetch has completed and ``resolve_inflight``
        has already been called.
        """
        if url:
            self._cache.pop(url, None)

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
