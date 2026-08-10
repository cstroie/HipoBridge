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
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import hippobridge
from hippobridge import serve_spec, get_cache_stats


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


if __name__ == "__main__":
    unittest.main()
