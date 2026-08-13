#!/usr/bin/env python3
"""Tests for sqlcache.SqliteCache — the SQLite-backed L2 cache that replaced
urlcache.FilesystemCache (one table per endpoint kind, plus cache_ai)."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import concurrent.futures
import tempfile
import time
import unittest

from sqlcache import SqliteCache, AiCacheView, route, RAW_HTML_TABLES


# One representative URL per named table (route() coverage), plus one
# unmatched URL to exercise the cache_other fallback.
_SAMPLE_URLS = {
    'cache_patient': ('http://x/Pacient/edit.asp?id=42', '42'),
    'cache_episode': ('http://x/Pacient/analysesEpisod.asp?pacid=42&strDomeniu=1&NrPePag=100', '42:1:'),
    'cache_checkout': ('http://x/gen_printabile/BiletExternare.asp?RelId=7&RelName=CO', '7'),
    'cache_checkin': ('http://x/files/checkin.asp?id=11', '11'),
    'cache_checkup': ('http://x/files/checkup.asp?cuid=99', '99'),
    'cache_cerere': ('http://x/PARA/NOM/Listare/cerere.asp?id=5', '5'),
    'cache_presentation': ('http://x/gen_printabile/FisaPrezentare.asp?relname=PR&id=3', '3'),
    'cache_report_buletin': ('http://x/PARA/Printabile/BuletinAnalize.asp?id=8&type=1&IdP=1', '8'),
    'cache_imaging_buletin': ('http://x/PARA/Printabile/BuletinAnalize.asp?id=8&type=3&IdP=1', '8'),
    'cache_solicitare': ('http://x/PARA/Printabile/BuletinSolicitare.asp?id=6&type=63&IdP=70', '6'),
    'cache_other': ('http://x/some/unmapped/page.asp', None),
}


class TestRoute(unittest.TestCase):

    def test_routes_each_known_table(self):
        for table, (url, key) in _SAMPLE_URLS.items():
            with self.subTest(table=table):
                self.assertEqual(route(url), (table, key))

    def test_episode_composite_key_with_year(self):
        url = 'http://x/Pacient/analysesEpisod.asp?pacid=42&strDomeniu=1&strAN=2024&NrPePag=100'
        self.assertEqual(route(url), ('cache_episode', '42:1:2024'))

    def test_buletin_type_split(self):
        report_url = 'http://x/PARA/Printabile/BuletinAnalize.asp?id=1&type=1&IdP=1'
        imaging_url = 'http://x/PARA/Printabile/BuletinAnalize.asp?id=1&type=3&IdP=1'
        self.assertEqual(route(report_url)[0], 'cache_report_buletin')
        self.assertEqual(route(imaging_url)[0], 'cache_imaging_buletin')

    def test_unmatched_url_falls_back(self):
        table, key = route('http://x/totally/unknown.asp?a=1')
        self.assertEqual(table, 'cache_other')
        self.assertIsNone(key)


class TestSqliteCacheRoundTrip(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.cache = SqliteCache(os.path.join(self._tmpdir.name, 'cache.db'), ttl=86400)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_get_put_remove_round_trip_per_table(self):
        for table, (url, _key) in _SAMPLE_URLS.items():
            with self.subTest(table=table):
                self.assertIsNone(self.cache.get(url))
                self.cache.put(url, f'content-for-{table}')
                self.assertEqual(self.cache.get(url), f'content-for-{table}')
                self.cache.remove(url)
                self.assertIsNone(self.cache.get(url))

    def test_put_overwrites_existing_entry(self):
        url = _SAMPLE_URLS['cache_patient'][0]
        self.cache.put(url, 'first')
        self.cache.put(url, 'second')
        self.assertEqual(self.cache.get(url), 'second')

    def test_expired_entry_returns_none_and_is_deleted(self):
        expired_cache = SqliteCache(os.path.join(self._tmpdir.name, 'cache.db'), ttl=-1)
        url = _SAMPLE_URLS['cache_checkin'][0]
        expired_cache.put(url, 'stale')
        self.assertIsNone(expired_cache.get(url))
        self.assertIsNone(self.cache.get(url))  # shared file, confirms the row was deleted


class TestIterEntries(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.cache = SqliteCache(os.path.join(self._tmpdir.name, 'cache.db'), ttl=86400)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_yields_all_entries_by_default(self):
        self.cache.put('http://x/files/checkin.asp?id=1', 'content-a')
        self.cache.put('http://x/files/checkup.asp?cuid=2', 'content-b')

        entries = {(url, content) for url, content, _mtime in self.cache.iter_entries()}
        self.assertEqual(entries, {
            ('http://x/files/checkin.asp?id=1', 'content-a'),
            ('http://x/files/checkup.asp?cuid=2', 'content-b'),
        })

    def test_since_mtime_excludes_older_entries(self):
        self.cache.put('http://x/files/checkin.asp?id=1', 'old-content')
        cutoff = time.time()
        time.sleep(0.01)
        self.cache.put('http://x/files/checkup.asp?cuid=2', 'new-content')

        urls = {url for url, _content, _mtime in self.cache.iter_entries(since_mtime=cutoff)}
        self.assertEqual(urls, {'http://x/files/checkup.asp?cuid=2'})

    def test_since_mtime_zero_is_equivalent_to_default(self):
        self.cache.put('http://x/files/checkin.asp?id=1', 'content-a')
        default_urls = {u for u, _c, _m in self.cache.iter_entries()}
        zero_urls = {u for u, _c, _m in self.cache.iter_entries(since_mtime=0.0)}
        self.assertEqual(default_urls, zero_urls)

    def test_expired_entries_excluded_regardless_of_cursor(self):
        expired_cache = SqliteCache(os.path.join(self._tmpdir.name, 'cache.db'), ttl=-1)
        expired_cache.put('http://x/files/checkin.asp?id=1', 'stale')
        self.assertEqual(list(self.cache.iter_entries()), [])

    def test_excludes_ai_cache_entries(self):
        self.cache.put('http://x/files/checkin.asp?id=1', 'raw-html')
        self.cache.put_ai('report:deadbeef', 'report', 'ai summary text', ttl=86400)
        urls = {url for url, _c, _m in self.cache.iter_entries()}
        self.assertEqual(urls, {'http://x/files/checkin.asp?id=1'})


class TestCleanup(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_deletes_only_expired_entries(self):
        db = os.path.join(self._tmpdir.name, 'cache.db')
        live = SqliteCache(db, ttl=86400)
        live.put('http://x/files/checkin.asp?id=1', 'fresh')

        expired = SqliteCache(db, ttl=-1)
        expired.put('http://x/files/checkup.asp?cuid=2', 'stale')

        result = live.cleanup(max_age_days=0)
        self.assertEqual(result['deleted'], 1)
        self.assertGreater(result['freed_bytes'], 0)
        self.assertEqual(live.get('http://x/files/checkin.asp?id=1'), 'fresh')

    def test_hard_max_age_cutoff_deletes_unexpired_entries(self):
        db = os.path.join(self._tmpdir.name, 'cache.db')
        cache = SqliteCache(db, ttl=86400, max_age_days=30)
        cache.put('http://x/files/checkin.asp?id=1', 'content')
        # Backdate cached_at past the hard cutoff directly via the shared connection.
        with cache._lock:
            cache._con.execute(
                "UPDATE cache_checkin SET cached_at = ? WHERE url = ?",
                (time.time() - 31 * 86400, 'http://x/files/checkin.asp?id=1'))
            cache._con.commit()
        result = cache.cleanup()
        self.assertEqual(result['deleted'], 1)


class TestStats(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.cache = SqliteCache(os.path.join(self._tmpdir.name, 'cache.db'), ttl=86400)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_aggregate_and_by_table_counts(self):
        self.cache.put('http://x/files/checkin.asp?id=1', 'aaa')
        self.cache.put('http://x/files/checkin.asp?id=2', 'bb')
        self.cache.put('http://x/files/checkup.asp?cuid=1', 'c')

        stats = self.cache.stats()
        self.assertEqual(stats['entries'], 3)
        self.assertEqual(stats['size_bytes'], len('aaa') + len('bb') + len('c'))
        self.assertEqual(stats['expired'], 0)
        self.assertIsNotNone(stats['oldest'])
        self.assertIsNotNone(stats['newest'])
        self.assertEqual(stats['by_table']['cache_checkin'], 2)
        self.assertEqual(stats['by_table']['cache_checkup'], 1)
        self.assertEqual(stats['by_table']['cache_patient'], 0)
        self.assertEqual(set(stats['by_table']), set(RAW_HTML_TABLES))

    def test_ai_entries_excluded_from_stats(self):
        self.cache.put_ai('report:aaa', 'report', 'summary', ttl=86400)
        stats = self.cache.stats()
        self.assertEqual(stats['entries'], 0)


class TestConcurrency(unittest.TestCase):

    def test_concurrent_put_get_does_not_raise(self):
        tmpdir = tempfile.TemporaryDirectory()
        try:
            cache = SqliteCache(os.path.join(tmpdir.name, 'cache.db'), ttl=86400)

            def worker(i):
                url = f'http://x/files/checkin.asp?id={i}'
                cache.put(url, f'content-{i}')
                return cache.get(url)

            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
                results = list(pool.map(worker, range(64)))
            self.assertEqual(results, [f'content-{i}' for i in range(64)])
        finally:
            tmpdir.cleanup()


class TestAiCache(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.cache = SqliteCache(os.path.join(self._tmpdir.name, 'cache.db'), ttl=86400)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_get_put_remove_round_trip(self):
        key = 'report:deadbeef'
        self.assertIsNone(self.cache.get_ai(key))
        self.cache.put_ai(key, 'report', 'summary text', ttl=86400)
        self.assertEqual(self.cache.get_ai(key), 'summary text')
        self.cache.remove_ai(key)
        self.assertIsNone(self.cache.get_ai(key))

    def test_independent_of_raw_html_tables(self):
        self.cache.put('http://x/files/checkin.asp?id=1', 'raw')
        self.cache.put_ai('report:deadbeef', 'report', 'ai text', ttl=86400)
        self.assertEqual(self.cache.stats()['entries'], 1)  # raw-HTML only

    def test_ai_cache_view_adapter(self):
        view = AiCacheView(self.cache, ttl=86400)
        key = 'epicrisis:cafebabe'
        self.assertIsNone(view.get(key))
        view.put(key, 'summary via adapter')
        self.assertEqual(view.get(key), 'summary via adapter')
        self.assertEqual(self.cache.get_ai(key), 'summary via adapter')
        view.remove(key)
        self.assertIsNone(view.get(key))


if __name__ == '__main__':
    unittest.main()
