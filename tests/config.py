#!/usr/bin/env python3
"""Tests for the top-level config-file loaders: hippobridge.py's
load_config() and llm/config.py's init_llm(). Both share the same shape
(in-code defaults, optionally overlaid by a gitignored *.cfg file) — these
tests exercise the file-I/O path directly (missing file, present file,
malformed file), which the pure-dict-based tests in llm_client.py don't
touch."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import configparser
import subprocess
import tempfile
import unittest

from hippobridge import DEFAULT_CONFIG, load_config
from llm.config import LLM_DEFAULTS, init_llm


class TestHippobridgeLoadConfig(unittest.TestCase):
    def test_missing_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            config = load_config(os.path.join(d, 'does-not-exist.cfg'))
        self.assertEqual(config.get('server', 'port'), DEFAULT_CONFIG['server']['port'])
        self.assertEqual(config.get('hipocrate', 'service_url'), DEFAULT_CONFIG['hipocrate']['service_url'])

    def test_present_file_overrides_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'hippobridge.cfg')
            with open(path, 'w') as f:
                f.write("[server]\nport = 8080\n[hipocrate]\nservice_url = http://example/hipocrate\n")
            config = load_config(path)
        self.assertEqual(config.get('server', 'port'), '8080')
        self.assertEqual(config.get('hipocrate', 'service_url'), 'http://example/hipocrate')
        # Keys not present in the file keep their in-code default.
        self.assertEqual(config.get('server', 'host'), DEFAULT_CONFIG['server']['host'])

    def test_present_file_keeps_unset_sections_at_default(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'hippobridge.cfg')
            with open(path, 'w') as f:
                f.write("[server]\nport = 8080\n")
            config = load_config(path)
        self.assertEqual(config.get('radiology', 'allowed_radiologists'),
                          DEFAULT_CONFIG['radiology']['allowed_radiologists'])
        self.assertEqual(config.get('logging', 'file'), DEFAULT_CONFIG['logging']['file'])

    def test_malformed_file_raises_configparser_error(self):
        # Regression guard: a syntactically broken hippobridge.cfg (e.g. a
        # duplicate section, common after a bad hand-edit) is not caught —
        # it propagates as configparser.Error and crashes startup with an
        # explicit traceback rather than silently falling back to defaults.
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'hippobridge.cfg')
            with open(path, 'w') as f:
                f.write("[server]\nport = 1\n[server]\nport = 2\n")
            with self.assertRaises(configparser.Error):
                load_config(path)


class TestInitLlm(unittest.TestCase):
    def test_missing_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            config = init_llm(os.path.join(d, 'does-not-exist.cfg'))
        self.assertEqual(config.get('llm', 'provider'), LLM_DEFAULTS['llm']['provider'])
        self.assertEqual(config.get('provider:default', 'url'), LLM_DEFAULTS['provider:default']['url'])

    def test_present_file_overrides_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'llm.cfg')
            with open(path, 'w') as f:
                f.write("[llm]\nprovider = custom\n[provider:custom]\nurl = http://example/v1\n")
            config = init_llm(path)
        self.assertEqual(config.get('llm', 'provider'), 'custom')
        self.assertEqual(config.get('provider:custom', 'url'), 'http://example/v1')
        # The built-in provider:default section still exists alongside it.
        self.assertTrue(config.has_section('provider:default'))

    def test_malformed_file_raises_configparser_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'llm.cfg')
            with open(path, 'w') as f:
                f.write("[llm]\nprovider = x\n[llm]\nprovider = y\n")
            with self.assertRaises(configparser.Error):
                init_llm(path)


class TestGitignoreOnlyTracksExamples(unittest.TestCase):
    """Guards the root-anchored `/*.cfg` rule in .gitignore: every *.cfg file
    tracked in git must live under examples/ (the tracked reference copy),
    never in the project root (the real, site-specific, gitignored file). A
    future genuinely-trackable root .cfg file (e.g. a linter config) would
    otherwise be silently swallowed by a too-broad ignore rule without
    anyone noticing — this also guards the inverse: that the rule isn't
    accidentally narrowed to let a real root *.cfg slip into git."""

    def setUp(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        try:
            out = subprocess.run(
                ['git', 'ls-files', '*.cfg'],
                cwd=repo_root, capture_output=True, text=True, timeout=10, check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            self.skipTest(f"git not available or not a repo: {exc}")
        self.tracked = [line for line in out.stdout.splitlines() if line]

    def test_only_examples_directory_cfg_files_are_tracked(self):
        outside_examples = [f for f in self.tracked if not f.startswith('examples/')]
        self.assertEqual(outside_examples, [],
                          f"real, site-specific *.cfg files must not be tracked in git: {outside_examples}")

    def test_expected_example_files_are_tracked(self):
        expected = {'examples/hippobridge.cfg', 'examples/llm.cfg',
                    'examples/regions.cfg', 'examples/worklist.cfg'}
        self.assertEqual(set(self.tracked), expected)


if __name__ == "__main__":
    unittest.main()
