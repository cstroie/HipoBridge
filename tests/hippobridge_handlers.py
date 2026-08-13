#!/usr/bin/env python3
"""Regression tests for two hippobridge.py route handlers whose blocking
file-I/O was moved off the event loop:

- serve_spec(): now loads spec.json once at import time (_SPEC_TEMPLATE)
  instead of re-reading it from disk on every request. The regression risk
  is the per-request deep copy: a shallow copy would leave servers[0] as a
  shared mutable dict, so concurrent requests with different scheme/host
  would clobber each other's URL.
- get_cache_stats(): now runs FilesystemCache.stats() (which walks every
  file in the cache dir) via run_in_executor instead of directly on the
  event loop, matching post_cache_cleanup()'s existing pattern.

Uses the handlers' __wrapped__ attribute (set by @functools.wraps inside
require_auth) to call get_cache_stats directly, bypassing the auth check —
these tests exercise the handler logic, not the auth decorator."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import hippobridge
import hippoclient
import search
from hippobridge import serve_spec, get_cache_stats
from hippodata import HippoData


def _run(coro):
    """Run coro to completion on a fresh event loop in a separate thread —
    keeps this file a plain unittest.TestCase (see tests/hippoclient_write.py
    for why: runtests.py already drives everything through one asyncio.run())."""
    with ThreadPoolExecutor(1) as ex:
        return ex.submit(asyncio.run, coro).result()


def _fake_request(scheme="http", host="example.test"):
    return SimpleNamespace(scheme=scheme, host=host)


class TestServeSpec(unittest.TestCase):
    def test_spec_template_loaded_at_import(self):
        self.assertIsNotNone(hippobridge._SPEC_TEMPLATE)
        self.assertIn("servers", hippobridge._SPEC_TEMPLATE)

    def test_response_url_matches_request(self):
        resp = _run(serve_spec(_fake_request(scheme="https", host="hb.example")))
        body = json.loads(resp.body)
        self.assertEqual(body["servers"][0]["url"], "https://hb.example")

    def test_concurrent_requests_do_not_leak_url_into_each_other(self):
        # Regression guard: a shallow copy of _SPEC_TEMPLATE would share the
        # same servers[0] dict across requests, so the second call's URL
        # patch would leak into the first response too.
        resp_a = _run(serve_spec(_fake_request(host="host-a.test")))
        resp_b = _run(serve_spec(_fake_request(host="host-b.test")))
        body_a = json.loads(resp_a.body)
        body_b = json.loads(resp_b.body)
        self.assertEqual(body_a["servers"][0]["url"], "http://host-a.test")
        self.assertEqual(body_b["servers"][0]["url"], "http://host-b.test")

    def test_template_itself_is_never_mutated(self):
        before = hippobridge._SPEC_TEMPLATE["servers"][0]["url"]
        _run(serve_spec(_fake_request(host="mutation-check.test")))
        after = hippobridge._SPEC_TEMPLATE["servers"][0]["url"]
        self.assertEqual(before, after)


class _StubFsCache:
    def __init__(self, stats_result):
        self._stats_result = stats_result
        self.stats_called = False

    def stats(self):
        self.stats_called = True
        return self._stats_result


class TestGetCacheStats(unittest.TestCase):
    def test_disabled_when_no_fs_cache(self):
        with patch.object(hippobridge.url_cache, "fs_cache", None):
            resp = _run(get_cache_stats.__wrapped__(_fake_request()))
        self.assertEqual(json.loads(resp.body), {"enabled": False})

    def test_returns_stats_via_executor(self):
        stub = _StubFsCache({"entries": 3, "size_bytes": 42})
        with patch.object(hippobridge.url_cache, "fs_cache", stub):
            resp = _run(get_cache_stats.__wrapped__(_fake_request()))
        self.assertTrue(stub.stats_called)
        self.assertEqual(json.loads(resp.body), {"enabled": True, "entries": 3, "size_bytes": 42})


class _StubFsCacheEntries:
    """Minimal stand-in for urlcache.FilesystemCache — only iter_entries()
    is used by _backfill_search_sync(). Entries are given increasing
    mtimes (start, start+1, ...) in the order passed, mirroring real cache
    files getting fresher timestamps as they're written, so tests can
    exercise the since_mtime cursor without hardcoding real timestamps."""
    def __init__(self, entries, start=1.0):
        self._entries = [(url, content, start + i) for i, (url, content) in enumerate(entries)]

    def iter_entries(self, since_mtime=0.0):
        for url, content, mtime in self._entries:
            if mtime > since_mtime:
                yield url, content, mtime


class TestBackfillSearch(unittest.TestCase):
    """_backfill_search_sync() scans cached pages for checkout/imaging
    report text (see search.py's module docstring for why this hooks
    hippoclient.py's parse_data() rather than a hippobridge.py route)."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.idx = search.SearchIndex(os.path.join(self._tmpdir.name, 'search.db'))

    def tearDown(self):
        self._tmpdir.cleanup()

    def _co_data(self, epicrisis='Diagnostic: gastroenterita acuta, evolutie buna.'):
        d = HippoData(status='success', message='')
        d.store('checkout.epicrisis', epicrisis)
        d.store('patient.cnp', 'CNP1')
        d.store('patient.name', 'Name1')
        return d

    def _im_data(self, result='CT abdomen: fara modificari patologice.'):
        d = HippoData(status='success', message='')
        d.store_list('studies', [{'result': result}])
        d.store('patient.cnp', 'CNP1')
        d.store('patient.name', 'Name1')
        return d

    def test_indexes_checkout_and_imaging_skips_lab_and_unrelated(self):
        fs = _StubFsCacheEntries([
            ('http://x/gen_printabile/BiletExternare.asp?RelId=555&RelName=CO', '<html>co</html>'),
            ('http://x/PARA/Printabile/BuletinAnalize.asp?id=777&type=3&IdP=1', '<html>im</html>'),
            ('http://x/PARA/Printabile/BuletinAnalize.asp?id=888&type=1&IdP=1', '<html>lab, must skip</html>'),
            ('http://x/files/search.asp?what=PA', '<html>unrelated, must skip</html>'),
        ])
        with patch.object(hippoclient.HippoClientCheckout, 'parse_data', return_value=self._co_data()), \
             patch.object(hippoclient.HippoClientImagingStudy, 'parse_data', return_value=self._im_data()):
            result = hippobridge._backfill_search_sync(fs, self.idx)

        self.assertEqual(result, {'scanned': 4, 'indexed': 2})
        self.assertEqual(len(_run(self.idx.search('gastroenterita'))), 1)
        self.assertEqual(len(_run(self.idx.search('abdomen'))), 1)

    def test_repeat_run_advances_cursor_so_theres_nothing_left_to_scan(self):
        fs = _StubFsCacheEntries([
            ('http://x/gen_printabile/BiletExternare.asp?RelId=555&RelName=CO', '<html>co</html>'),
        ])
        with patch.object(hippoclient.HippoClientCheckout, 'parse_data', return_value=self._co_data()):
            first = hippobridge._backfill_search_sync(fs, self.idx)
            second = hippobridge._backfill_search_sync(fs, self.idx)

        self.assertEqual(first, {'scanned': 1, 'indexed': 1})
        # Cursor advanced past this entry's mtime — iter_entries yields
        # nothing at all on the second pass, not just "skipped after scan".
        self.assertEqual(second, {'scanned': 0, 'indexed': 0})

    def test_already_indexed_entry_skipped_without_reparsing_even_if_rescanned(self):
        # A file that's already indexed but shows up again with a newer
        # mtime (e.g. Hipocrate re-served the same unchanged page) should
        # still be scanned (the cursor doesn't filter it out) but must not
        # be re-parsed/re-indexed — the existing-keys check should short-
        # circuit before parse_data() is ever called.
        fs1 = _StubFsCacheEntries([
            ('http://x/gen_printabile/BiletExternare.asp?RelId=555&RelName=CO', '<html>co</html>'),
        ], start=1.0)
        with patch.object(hippoclient.HippoClientCheckout, 'parse_data', return_value=self._co_data()):
            hippobridge._backfill_search_sync(fs1, self.idx)

        fs2 = _StubFsCacheEntries([
            ('http://x/gen_printabile/BiletExternare.asp?RelId=555&RelName=CO', '<html>co again</html>'),
        ], start=5.0)  # newer than the cursor left behind by fs1's run
        with patch.object(hippoclient.HippoClientCheckout, 'parse_data') as mock_parse:
            result = hippobridge._backfill_search_sync(fs2, self.idx)

        self.assertEqual(result, {'scanned': 1, 'indexed': 0})
        mock_parse.assert_not_called()

    def test_empty_epicrisis_is_not_indexed(self):
        fs = _StubFsCacheEntries([
            ('http://x/gen_printabile/BiletExternare.asp?RelId=999&RelName=CO', '<html>co</html>'),
        ])
        with patch.object(hippoclient.HippoClientCheckout, 'parse_data', return_value=self._co_data(epicrisis='')):
            result = hippobridge._backfill_search_sync(fs, self.idx)
        self.assertEqual(result, {'scanned': 1, 'indexed': 0})

    def test_parse_failure_on_one_entry_does_not_abort_the_scan(self):
        fs = _StubFsCacheEntries([
            ('http://x/gen_printabile/BiletExternare.asp?RelId=1&RelName=CO', '<html>broken</html>'),
            ('http://x/gen_printabile/BiletExternare.asp?RelId=2&RelName=CO', '<html>ok</html>'),
        ])
        with patch.object(hippoclient.HippoClientCheckout, 'parse_data',
                           side_effect=[RuntimeError("malformed page"), self._co_data()]):
            result = hippobridge._backfill_search_sync(fs, self.idx)
        self.assertEqual(result, {'scanned': 2, 'indexed': 1})

    def test_async_wrapper_noop_when_index_not_configured(self):
        with patch.object(search, 'instance', None):
            # Should not raise even though url_cache.fs_cache may be set —
            # both must be configured.
            _run(hippobridge._backfill_search())


if __name__ == "__main__":
    unittest.main()
