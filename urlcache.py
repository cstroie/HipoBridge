#!/usr/bin/env python3
"""URL cache implementation for HTTP response caching with LRU eviction and timeout.

This module provides a simple in-memory cache for HTTP responses with automatic
expiration based on configurable timeout periods. It implements a basic Least 
Recently Used (LRU) cache for storing HTTP response content.
"""

from typing import Dict, Optional
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)8s | %(message)s'
)
logger = logging.getLogger('URLCache')


class URLCache:
    """Simple in-memory cache for HTTP responses with LRU eviction and timeout.

    Implements a basic Least Recently Used (LRU) cache for storing HTTP response
    content with automatic expiration based on configurable timeout periods.
    """

    def __init__(self, max_size: int = 100, timeout: int = 600):
        """Initialize the cache.

        Args:
            max_size: Maximum number of entries to cache (default: 100)
            timeout: Cache timeout in seconds (default: 600 seconds/10 minutes)
        """
        self.max_size = max_size
        self.timeout = timeout
        self.cache: Dict[str, str] = {}
        self.timestamps: Dict[str, datetime] = {}

    def get(self, url: str) -> Optional[str]:
        """Get cached response for URL if exists and not expired.

        Retrieves cached content for a URL if it exists and hasn't expired
        based on the configured timeout value.

        Args:
            url: URL to lookup in cache

        Returns:
            Cached response text or None if not found or expired
        """
        if url not in self.cache:
            return None

        # Check if cache entry is still valid
        if url in self.timestamps:
            cache_age = (datetime.now() - self.timestamps[url]).total_seconds()
            if cache_age >= self.timeout:
                # Cache entry expired, remove it
                del self.cache[url]
                del self.timestamps[url]
                logger.debug(f"Expired cache entry removed for: {url}")
                return None
        # Return cached response
        logger.debug(f"Using cached response for: {url} (age: {(datetime.now() - self.timestamps[url]).total_seconds():.1f}s)")
        return self.cache[url]

    def put(self, url: str, response_text: str) -> None:
        """Add response to cache, evicting oldest entry if needed.

        Stores response text in cache with current timestamp. If cache is at
        maximum capacity, the oldest entry is automatically removed.

        Args:
            url: URL key for caching
            response_text: Response text to cache
        """
        # If cache is at max size, remove the oldest entry
        if len(self.cache) >= self.max_size:
            # Remove the first (oldest) entry
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            if oldest_key in self.timestamps:
                del self.timestamps[oldest_key]
        # Add the new entry with timestamp
        self.cache[url] = response_text
        self.timestamps[url] = datetime.now()
        logger.debug(f"Cached response for: {url}")

    def remove(self, url: str) -> None:
        """Remove specific cache entry.

        Removes a specific URL's cached content if it exists.

        Args:
            url: Specific URL to remove from cache
        """
        if url:
            if url in self.cache:
                del self.cache[url]
            if url in self.timestamps:
                del self.timestamps[url]

    def clear(self) -> None:
        """Clear all cache entries.

        Removes all cached content from the cache.
        """
        self.cache.clear()
        self.timestamps.clear()
