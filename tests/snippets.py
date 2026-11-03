#!/usr/bin/env python3
"""Tests for report-editor snippet loading (snippets.cfg)."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import tempfile
import unittest

from snippets import load_snippets, get_snippets


class TestLoadSnippets(unittest.TestCase):
    def _write(self, d, text):
        path = os.path.join(d, 'snippets.cfg')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        return path

    def test_missing_file_is_empty(self):
        self.assertEqual(load_snippets('/nonexistent/snippets.cfg'), {})

    def test_parses_names_lowercased_and_percent_safe(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, "[ultrasound]\nApendice = Diametru $0 mm, 100% normal ț\n")
            self.assertEqual(load_snippets(p), {'ultrasound': {'apendice': 'Diametru $0 mm, 100% normal ț'}})

    def test_multiline_value(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, "[ct]\nnorm = linia 1\n  linia 2\n")
            self.assertEqual(load_snippets(p), {'ct': {'norm': 'linia 1\nlinia 2'}})

    def test_backslash_n_is_newline(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, "[ct]\nnorm = a\\nb\\n\\nc\n")
            self.assertEqual(load_snippets(p), {'ct': {'norm': 'a\nb\n\nc'}})

    def test_broken_file_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(load_snippets(self._write(d, "garbage without section\n")), {})

    def test_get_snippets_rereads_on_change(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, "[common]\na = one\n")
            self.assertEqual(get_snippets('eco', p), {'a': 'one'})
            self._write(d, "[common]\na = two\n")
            os.utime(p, ns=(1, 2_000_000_000))
            self.assertEqual(get_snippets('eco', p), {'a': 'two'})

    def test_modality_overrides_common_and_is_isolated(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, "[common]\nabd = c\nx = common\n[ultrasound]\nabd = us\n[radiography]\nabd = xr\n")
            self.assertEqual(get_snippets('eco', p), {'abd': 'us', 'x': 'common'})
            self.assertEqual(get_snippets('radio', p), {'abd': 'xr', 'x': 'common'})
            self.assertEqual(get_snippets('ct', p), {'abd': 'c', 'x': 'common'})
            self.assertEqual(get_snippets('', p), {'abd': 'c', 'x': 'common'})


if __name__ == '__main__':
    unittest.main()
