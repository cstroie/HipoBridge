#!/usr/bin/env python3
"""Tests for search.py — the local full-text index over epicrisis/
imaging report text (no server needed, no Hipocrate network calls).

Plain (synchronous) unittest.TestCase, not IsolatedAsyncioTestCase — see
tests/hippoclient_write.py's module docstring for why: runtests.py drives
everything through its own single asyncio.run() call, and
IsolatedAsyncioTestCase tries to start a second event loop in the same
thread, which asyncio forbids. _run() below runs each coroutine to
completion in a throwaway thread instead."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import sqlite3
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from search import SearchIndex


def _run(coro):
    """Run coro to completion on a fresh event loop in a separate thread."""
    with ThreadPoolExecutor(1) as ex:
        return ex.submit(asyncio.run, coro).result()


class TestSearchIndex(unittest.TestCase):
    """Test cases for SearchIndex."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmpdir.name, 'search.db')
        self.index = SearchIndex(self.db_path, max_age_days=30)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_index_and_search_round_trip(self):
        _run(self.index.index_document(
            'epicrisis', 'CO1', '1234567890123', 'Ionescu Maria',
            'Diagnostic: pneumonie dreapta, cauza oncologica suspicionata.'))

        results = _run(self.index.search('oncologica'))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['kind'], 'epicrisis')
        self.assertEqual(results[0]['source_id'], 'CO1')
        self.assertEqual(results[0]['patient_cnp'], '1234567890123')
        self.assertEqual(results[0]['patient_name'], 'Ionescu Maria')
        self.assertIn('<mark>oncologica</mark>', results[0]['snippet'])

    def test_snippet_length(self):
        text = ' '.join(f'cuvant{i}' for i in range(100)) + ' oncologica ' + ' '.join(f'dupa{i}' for i in range(100))
        _run(self.index.index_document('epicrisis', 'CO1', '1', 'A', text))

        short = _run(self.index.search('oncologica'))[0]['snippet']
        long_ = _run(self.index.search('oncologica', snippet_length=40))[0]['snippet']
        self.assertLess(len(short.split()), len(long_.split()))
        self.assertIn('<mark>oncologica</mark>', long_)
        # out-of-range values are clamped, not an FTS5 error
        _run(self.index.search('oncologica', snippet_length=1000))
        _run(self.index.search('oncologica', snippet_length=0))

    def test_hits_are_grouped_by_patient(self):
        for i in range(3):
            _run(self.index.index_document('epicrisis', f'E{i}', 'cnpA', 'Ana', 'rabdomiosarcom embrionar'))
        _run(self.index.index_document('imaging', 'I1', 'cnpA', 'Ana', 'pacient cu rabdomiosarcom'))
        _run(self.index.index_document('epicrisis', 'E9', 'cnpB', 'Bob', 'rabdomiosarcom'))

        results = _run(self.index.search('rabdomiosarcom'))
        self.assertEqual(len(results), 2)
        by = {r['patient_cnp']: r for r in results}
        self.assertEqual(by['cnpA']['count'], 4)
        self.assertEqual(by['cnpA']['kinds'], {'epicrisis': 3, 'imaging': 1})
        self.assertEqual(len(by['cnpA']['documents']), 4)
        self.assertEqual(by['cnpB']['count'], 1)

    def test_search_no_match(self):
        _run(self.index.index_document('imaging', 'IMG1', 'cnp', 'name', 'CT torace normal.'))
        results = _run(self.index.search('nonexistentterm12345'))
        self.assertEqual(results, [])

    def test_search_empty_query(self):
        _run(self.index.index_document('imaging', 'IMG1', 'cnp', 'name', 'CT torace normal.'))
        results = _run(self.index.search('   '))
        self.assertEqual(results, [])

    def test_diacritic_insensitive_match(self):
        _run(self.index.index_document('epicrisis', 'CO2', 'cnp', 'name', 'cauza ramane neclara'))
        # "cauzâ" (circumflex, not typed the same way) should still match "cauza"
        results = _run(self.index.search('cauzâ'))
        self.assertEqual(len(results), 1)

    def test_upsert_replaces_old_text(self):
        _run(self.index.index_document('epicrisis', 'CO3', 'cnp', 'name', 'text initial despre oncologie'))
        _run(self.index.index_document('epicrisis', 'CO3', 'cnp', 'name', 'text complet diferit'))

        self.assertEqual(_run(self.index.search('oncologie')), [])
        results = _run(self.index.search('diferit'))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['source_id'], 'CO3')

    def test_index_document_empty_text_is_noop(self):
        _run(self.index.index_document('epicrisis', 'CO_EMPTY', 'cnp', 'name', '   '))
        con = sqlite3.connect(self.db_path)
        try:
            count = con.execute("SELECT count(*) FROM documents WHERE source_id = 'CO_EMPTY'").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(count, 0)

    def test_cleanup_evicts_old_documents(self):
        _run(self.index.index_document('epicrisis', 'OLD1', 'cnp', 'name', 'text vechi despre pneumonie'))

        con = sqlite3.connect(self.db_path)
        try:
            con.execute("UPDATE documents SET updated_at = ? WHERE source_id = 'OLD1'",
                        (time.time() - 40 * 86400,))
            con.commit()
        finally:
            con.close()

        result = _run(self.index.cleanup(30))
        self.assertEqual(result['deleted'], 1)
        self.assertEqual(_run(self.index.search('pneumonie')), [])

        # No orphaned FTS rows left behind
        con = sqlite3.connect(self.db_path)
        try:
            fts_count = con.execute("SELECT count(*) FROM documents_fts").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(fts_count, 0)

    def test_cleanup_uses_instance_default_max_age(self):
        _run(self.index.index_document('epicrisis', 'OLD2', 'cnp', 'name', 'text vechi'))
        con = sqlite3.connect(self.db_path)
        try:
            con.execute("UPDATE documents SET updated_at = ? WHERE source_id = 'OLD2'",
                        (time.time() - 40 * 86400,))
            con.commit()
        finally:
            con.close()

        # No max_age_days argument — should fall back to self.max_age_days (30)
        result = _run(self.index.cleanup())
        self.assertEqual(result['deleted'], 1)

    def test_backfill_cursor_defaults_to_zero(self):
        self.assertEqual(self.index.get_backfill_cursor_sync(), 0.0)

    def test_backfill_cursor_round_trip(self):
        self.index.set_backfill_cursor_sync(12345.5)
        self.assertEqual(self.index.get_backfill_cursor_sync(), 12345.5)
        # Setting again should update in place, not error on the PK conflict.
        self.index.set_backfill_cursor_sync(99999.0)
        self.assertEqual(self.index.get_backfill_cursor_sync(), 99999.0)

    def _seed_passages(self):
        m = {'doc_date': '2026-03-02', 'modality': 'MR', 'title': 'RMN cerebral', 'status': 'final'}
        _run(self.index.index_document('imaging', '1', 'c1', 'A',
             'Leziune de substanță albă. Concluzii: meningiom frontal drept.', m))
        _run(self.index.index_document('epicrisis', '2', 'c2', 'B',
             'Meningioame multiple. Secvențe T2.', {'doc_date': '2025-01-05', 'status': 'final'}))
        _run(self.index.index_document('imaging', '3', 'c3', 'C', 'meningiom draft', {**m, 'status': 'draft'}))

    def test_passages_all_vs_any(self):
        self._seed_passages()
        self.assertEqual(_run(self.index.search_passages('meningiom flair')), [])
        any_ = _run(self.index.search_passages('meningiom flair', match='any'))
        self.assertEqual([d['source_id'] for d in any_], ['1'])
        self.assertEqual(_run(self.index.search_passages('meningiom flair', match='any', min_match=2)), [])

    def test_passages_final_only_and_filters(self):
        self._seed_passages()
        ids = lambda **kw: sorted(d['source_id'] for d in _run(self.index.search_passages('meningiom', match='any', **kw)))
        self.assertEqual(ids(), ['1'])                       # draft '3' hidden; '2' needs the prefix alt
        self.assertEqual(ids(status=None), ['1', '3'])
        self.assertEqual(ids(modalities=['CT'], status=None), [])
        self.assertEqual(ids(date_from='2026-03-03', status=None), [])

    def test_passages_alternatives_and_phrase(self):
        self._seed_passages()
        r = _run(self.index.search_passages('meningiom|meningioame t2', match='any', min_match=2))
        self.assertEqual([d['source_id'] for d in r], ['2'])
        r = _run(self.index.search_passages('"substanta alba"'))
        self.assertEqual([d['source_id'] for d in r], ['1'])
        self.assertIn('substanță albă', r[0]['passage'])

    def test_passages_hostile_query(self):
        self._seed_passages()
        for q in ('" OR (', 'NEAR(', '*', '"', '-meningiom'):
            _run(self.index.search_passages(q, match='any'))   # must not raise

    def test_legacy_rows_have_no_status_and_are_reindexed(self):
        _run(self.index.index_document('epicrisis', 'L', 'c', 'n', 'meningiom'))
        self.assertEqual(_run(self.index.search_passages('meningiom')), [])
        self.assertNotIn(('epicrisis', 'L'), self.index.indexed_keys_sync())


if __name__ == '__main__':
    unittest.main()
