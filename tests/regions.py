#!/usr/bin/env python3
"""Tests for region identification rule loading (regions.cfg)."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import logging
import tempfile
import unittest

from hippoclient import load_region_rules


_SAMPLE_CFG = """\
[radiography]
chest = toracica, pulmonara
abdomen = abdomenului

[ultrasound]
abdomen = abdominala
"""


class TestLoadRegionRules(unittest.TestCase):
    def test_parses_all_five_modalities(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'regions.cfg')
            with open(path, 'w') as f:
                f.write(_SAMPLE_CFG)
            radio, eco, ct, mri, fluoro = load_region_rules(path)
        self.assertEqual(radio, {'chest': ['toracica', 'pulmonara'], 'abdomen': ['abdomenului']})
        self.assertEqual(eco, {'abdomen': ['abdominala']})
        # Sections absent from the file come back as empty dicts, not KeyError.
        self.assertEqual(ct, {})
        self.assertEqual(mri, {})
        self.assertEqual(fluoro, {})

    def test_strips_whitespace_around_keywords(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'regions.cfg')
            with open(path, 'w') as f:
                f.write("[radiography]\nchest =  toracica ,  pulmonara \n")
            radio, *_ = load_region_rules(path)
        self.assertEqual(radio['chest'], ['toracica', 'pulmonara'])

    def test_missing_file_returns_all_empty_rules(self):
        with tempfile.TemporaryDirectory() as d:
            missing_path = os.path.join(d, 'does-not-exist.cfg')
            radio, eco, ct, mri, fluoro = load_region_rules(missing_path)
        self.assertEqual((radio, eco, ct, mri, fluoro), ({}, {}, {}, {}, {}))

    def test_missing_file_logs_warning(self):
        with tempfile.TemporaryDirectory() as d:
            missing_path = os.path.join(d, 'does-not-exist.cfg')
            with self.assertLogs('hippoclient', level='WARNING') as cm:
                load_region_rules(missing_path)
        self.assertTrue(any('not found' in msg for msg in cm.output[0:1] + cm.output))

    def test_empty_file_returns_all_empty_rules(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'regions.cfg')
            open(path, 'w').close()
            radio, eco, ct, mri, fluoro = load_region_rules(path)
        self.assertEqual((radio, eco, ct, mri, fluoro), ({}, {}, {}, {}, {}))


if __name__ == "__main__":
    unittest.main()
