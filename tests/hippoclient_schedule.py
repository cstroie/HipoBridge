#!/usr/bin/env python3
"""Tests for the Schedule ward filter's family grouping (first word of the
ward name) in HippoClientSchedule._ward_family/_apply_filters."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest

from hippoclient import HippoClientSchedule


class TestWardFamily(unittest.TestCase):
    def test_family_is_first_word(self):
        f = HippoClientSchedule._ward_family
        self.assertEqual(f('CHIRURGIE I'), 'CHIRURGIE')
        self.assertEqual(f('CHIRURGIE II'), 'CHIRURGIE')
        self.assertEqual(f('PEDIATRIE I'), 'PEDIATRIE')
        self.assertEqual(f('PEDIATRIE NEUROLOGIE'), 'PEDIATRIE')
        self.assertEqual(f('UPU'), 'UPU')
        self.assertEqual(f('  PEDIATRIE   II '), 'PEDIATRIE')
        self.assertEqual(f(''), '')


class TestApplyFiltersSection(unittest.TestCase):
    def setUp(self):
        self.client = HippoClientSchedule("http://test.invalid", None)
        self.requests = [
            {'section': 'PEDIATRIE I'},
            {'section': 'PEDIATRIE II'},
            {'section': 'PEDIATRIE NEUROLOGIE'},
            {'section': 'CARDIOLOGIE'},
            {'section': 'UPU'},
            {'section': None},
        ]

    def _sections(self, name):
        return [r['section'] for r in self.client._apply_filters(self.requests, section_name=name)]

    def test_family_matches_all_variants(self):
        self.assertEqual(self._sections('PEDIATRIE'),
                         ['PEDIATRIE I', 'PEDIATRIE II', 'PEDIATRIE NEUROLOGIE'])

    def test_exact_ward_matches_only_itself(self):
        self.assertEqual(self._sections('PEDIATRIE I'), ['PEDIATRIE I'])
        self.assertEqual(self._sections('UPU'), ['UPU'])

    def test_unknown_ward_is_empty(self):
        self.assertEqual(self._sections('ORTOPEDIE'), [])

    def test_no_section_filter_returns_all(self):
        self.assertEqual(len(self.client._apply_filters(self.requests, section_name=None)), 6)
        self.assertEqual(len(self.client._apply_filters(self.requests, section_name='')), 6)


if __name__ == "__main__":
    unittest.main()
