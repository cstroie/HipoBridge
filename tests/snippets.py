#!/usr/bin/env python3
"""Tests for report-editor snippet loading (snippets.cfg)."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import tempfile
import unittest

import snippets
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



class TestUserSnippets(unittest.TestCase):
    """A user's own snippets (snippets/<user>.json) over the shared snippets.cfg."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = os.path.join(self._tmp.name, 'users')
        self.cfg = os.path.join(self._tmp.name, 'snippets.cfg')
        with open(self.cfg, 'w', encoding='utf-8') as f:
            f.write("[common]\nsig = Dr. X\nabd = common abdomen\n[ultrasound]\nabd = shared us abdomen\n")

    def put(self, user, section, name, text, **kw):
        return snippets.set_snippet(user, section, name, text, user_dir=self.dir, **kw)

    def get(self, modality, user=''):
        return get_snippets(modality, self.cfg, user=user, user_dir=self.dir)

    def test_own_snippet_overrides_shared_for_that_user_only(self):
        self.put('ana', 'ultrasound', 'abd', 'ana abdomen')
        self.put('ana', 'common', 'new', 'line 1\r\nline 2')
        self.assertEqual(self.get('eco', 'ana'), {'sig': 'Dr. X', 'abd': 'ana abdomen', 'new': 'line 1\nline 2'})
        self.assertEqual(self.get('eco', 'bob'), {'sig': 'Dr. X', 'abd': 'shared us abdomen'})
        self.assertEqual(self.get('eco'), {'sig': 'Dr. X', 'abd': 'shared us abdomen'})
        # an own common snippet wins over the shared modality one
        self.put('bob', 'common', 'abd', 'bob everywhere')
        self.assertEqual(self.get('eco', 'bob')['abd'], 'bob everywhere')
        self.assertEqual(self.get('ct', 'bob')['abd'], 'bob everywhere')

    def test_delete_brings_the_shared_one_back(self):
        self.put('ana', 'ultrasound', 'abd', 'mine')
        self.assertTrue(snippets.delete_snippet('ana', 'ultrasound', 'abd', user_dir=self.dir))
        self.assertEqual(self.get('eco', 'ana')['abd'], 'shared us abdomen')
        self.assertFalse(snippets.delete_snippet('ana', 'ultrasound', 'abd', user_dir=self.dir))   # shared: not hers
        self.assertFalse(snippets.delete_snippet('ana', 'ultrasound', 'nope', user_dir=self.dir))

    def test_rename(self):
        self.put('ana', 'ct', 'a', 'text a')
        self.put('ana', 'ct', 'b', 'text b')
        self.assertEqual(self.put('ana', 'ct', ';C2', 'text c', rename_from='a'), 'c2')
        self.assertEqual(snippets.load_user('ana', self.dir), {'ct': {'b': 'text b', 'c2': 'text c'}})
        with self.assertRaises(snippets.SnippetError):       # the name of another own snippet
            self.put('ana', 'ct', 'b', 'x', rename_from='c2')

    def test_refused(self):
        for section, name, text in (('nope', 'a', 't'), ('ct', '', 't'), ('ct', 'a b', 't'), ('ct', '_a', 't'),
                                    ('ct', '../x', 't'), ('ct', 'a', '  '), ('ct', 'a' * 41, 't'),
                                    ('ct', 'a', 'x' * (snippets.MAX_TEXT + 1))):
            with self.assertRaises(snippets.SnippetError, msg=(section, name)):
                self.put('ana', section, name, text)
        with self.assertRaises(snippets.SnippetError):
            self.put('', 'ct', 'a', 't')
        self.assertEqual(snippets.clean_name(' ;Țesut-2 '), 'țesut-2')

    def test_list_all_marks_own_and_shared(self):
        self.put('ana', 'ultrasound', 'abd', 'mine')
        self.put('ana', 'ultrasound', 'zz', 'only mine')
        out = snippets.list_all('ana', self.cfg, self.dir)
        self.assertEqual([s['id'] for s in out['sections']],
                         ['common', 'ultrasound', 'radiography', 'ct', 'mri', 'fluoroscopy'])
        us = out['sections'][1]['snippets']
        self.assertEqual(us, [{'name': 'abd', 'text': 'mine', 'mine': True, 'shared': 'shared us abdomen'},
                              {'name': 'zz', 'text': 'only mine', 'mine': True, 'shared': None}])
        self.assertEqual(out['sections'][0]['snippets'][1],
                         {'name': 'sig', 'text': 'Dr. X', 'mine': False, 'shared': 'Dr. X'})

    def test_username_cannot_leave_the_directory(self):
        self.put('../../evil', 'ct', 'a', 't')
        self.put('.hidden', 'ct', 'a', 't')
        self.put('ion.pop', 'ct', 'a', 't')
        names = sorted(os.listdir(self.dir))
        self.assertEqual(len(names), 3)
        self.assertTrue(all(n.endswith('.json') and '/' not in n and not n.startswith('.') for n in names), names)
        self.assertIn('ion.pop.json', names)
        self.assertEqual(os.listdir(self._tmp.name).count('evil.json'), 0)
        self.assertEqual(snippets.load_user('../../evil', self.dir), {'ct': {'a': 't'}})

    def test_broken_user_file_is_empty(self):
        os.makedirs(self.dir)
        with open(os.path.join(self.dir, 'ana.json'), 'w') as f:
            f.write('{not json')
        self.assertEqual(snippets.load_user('ana', self.dir), {})
        self.assertEqual(self.get('eco', 'ana')['abd'], 'shared us abdomen')


if __name__ == '__main__':
    unittest.main()
