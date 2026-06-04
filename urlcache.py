#!/usr/bin/env python3
"""URL cache implementation for HTTP response caching with LRU eviction and timeout.

This module provides a simple in-memory cache for HTTP responses with automatic
expiration based on configurable timeout periods. It implements a basic Least
Recently Used (LRU) cache for storing HTTP response content, with in-flight
request deduplication to prevent cache stampedes under concurrent load.
"""

import asyncio
from typing import Dict, Optional
import logging
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)8s | %(message)s'
)
logger = logging.getLogger('URLCache')


class URLCache:
    """In-memory cache for HTTP responses with LRU eviction, timeout, and stampede prevention.

    Stores HTTP response text keyed by URL. When a URL is being fetched by one
    coroutine, subsequent requests for the same URL wait for the in-flight result
    rather than issuing redundant upstream requests.
    """

    def __init__(self, max_size: int = 500, timeout: int = 1800):
        """Initialize the cache.

        Args:
            max_size: Maximum number of entries to cache (default: 500)
            timeout: Cache timeout in seconds (default: 1800 seconds / 30 minutes)
        """
        self.max_size = max_size
        self.timeout = timeout
        self.cache: Dict[str, str] = {}
        self.timestamps: Dict[str, datetime] = {}
        # Maps URL → asyncio.Event for in-flight deduplication
        self._inflight: Dict[str, asyncio.Event] = {}

    def get(self, url: str) -> Optional[str]:
        """Get cached response for URL if it exists and has not expired.

        Args:
            url: URL to lookup in cache

        Returns:
            Cached response text or None if not found or expired
        """
        if url not in self.cache:
            return None

        ts = self.timestamps.get(url)
        if ts is None:
            # Orphaned cache entry — remove and treat as miss
            del self.cache[url]
            return None

        cache_age = (datetime.now(timezone.utc) - ts).total_seconds()
        if cache_age >= self.timeout:
            del self.cache[url]
            del self.timestamps[url]
            logger.debug(f"Expired cache entry removed for: {url}")
            return None

        logger.debug(f"Cache hit for: {url} (age: {cache_age:.1f}s)")
        return self.cache[url]

    def put(self, url: str, response_text: str) -> None:
        """Add response to cache, evicting the oldest entry if at capacity.

        Args:
            url: URL key for caching
            response_text: Response text to cache
        """
        if len(self.cache) >= self.max_size:
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            self.timestamps.pop(oldest_key, None)
            logger.debug(f"Evicted oldest cache entry: {oldest_key}")
        self.cache[url] = response_text
        self.timestamps[url] = datetime.now(timezone.utc)
        logger.debug(f"Cached response for: {url}")

    def remove(self, url: str) -> None:
        """Remove a specific cache entry.

        Args:
            url: URL to remove from cache
        """
        if url:
            self.cache.pop(url, None)
            self.timestamps.pop(url, None)

    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()
        self.timestamps.clear()
        self._inflight.clear()

    def is_inflight(self, url: str) -> bool:
        """Return True if a fetch for this URL is already in progress."""
        return url in self._inflight

    def mark_inflight(self, url: str) -> asyncio.Event:
        """Register a URL as being fetched. Returns the Event other waiters should await."""
        event = asyncio.Event()
        self._inflight[url] = event
        return event

    def resolve_inflight(self, url: str) -> None:
        """Mark the in-flight fetch as complete and wake up any waiters."""
        event = self._inflight.pop(url, None)
        if event:
            event.set()

    async def wait_inflight(self, url: str) -> None:
        """Wait until the in-flight fetch for url completes (or is abandoned)."""
        event = self._inflight.get(url)
        if event:
            await event.wait()
