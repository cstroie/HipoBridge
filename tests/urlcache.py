#!/usr/bin/env python3
"""Tests for urlcache.FilesystemCache.iter_entries() — the since_mtime
cursor support added for hippobridge.py's periodic search-index backfill
(see search_index.py's module docstring)."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import tempfile
import time
import unittest

from urlcache import FilesystemCache


class TestFilesystemCacheIterEntries(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.cache = FilesystemCache(self._tmpdir.name, ttl=86400)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_yields_all_entries_by_default(self):
        self.cache.put('http://x/a', 'content-a')
        self.cache.put('http://x/b', 'content-b')

        entries = {(url, content) for url, content, _mtime in self.cache.iter_entries()}
        self.assertEqual(entries, {('http://x/a', 'content-a'), ('http://x/b', 'content-b')})

    def test_since_mtime_excludes_older_entries(self):
        self.cache.put('http://x/old', 'old-content')
        cutoff = time.time()
        time.sleep(0.01)
        self.cache.put('http://x/new', 'new-content')

        urls = {url for url, _content, _mtime in self.cache.iter_entries(since_mtime=cutoff)}
        self.assertEqual(urls, {'http://x/new'})

    def test_since_mtime_zero_is_equivalent_to_default(self):
        self.cache.put('http://x/a', 'content-a')
        default_urls = {u for u, _c, _m in self.cache.iter_entries()}
        zero_urls = {u for u, _c, _m in self.cache.iter_entries(since_mtime=0.0)}
        self.assertEqual(default_urls, zero_urls)

    def test_expired_entries_excluded_regardless_of_cursor(self):
        expired_cache = FilesystemCache(self._tmpdir.name, ttl=-1)  # already expired on write
        expired_cache.put('http://x/expired', 'stale')
        self.assertEqual(list(self.cache.iter_entries()), [])


if __name__ == '__main__':
    unittest.main()
