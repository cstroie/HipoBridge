#!/usr/bin/env python3
"""Tests for the LLM provider config and prompt registry (no server needed)."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import configparser
import unittest

from llm.config import LLM_DEFAULTS, TIERS, select_provider
from llm.prompts import PROMPTS


def _config(overlay: dict | None = None) -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    config.read_dict(LLM_DEFAULTS)
    if overlay:
        config.read_dict(overlay)
    return config


class TestProviderSelection(unittest.TestCase):
    def test_default_provider(self):
        url, key, models = select_provider(_config())
        self.assertEqual(url, "http://127.0.0.1:8080/v1")
        self.assertEqual(key, "")
        self.assertEqual(set(models), set(TIERS))
        self.assertTrue(all(models[t] for t in TIERS))

    def test_local_override_switches_provider(self):
        # Mirrors local.cfg adding a second provider and repointing [llm].
        config = _config({
            "llm": {"provider": "lmstudio"},
            "provider:lmstudio": {
                "url": "http://192.168.3.238:1234/v1",
                "key": "",
                "lite": "LFM2.5-230M",
                "default": "LFM2-2.6B-Transcript",
                "medical": "medgemma-4b-it",
            },
        })
        url, _key, models = select_provider(config)
        self.assertEqual(url, "http://192.168.3.238:1234/v1")
        self.assertEqual(models["medical"], "medgemma-4b-it")

    def test_key_is_read(self):
        config = _config({"provider:default": {"key": "sk-abc"}})
        _url, key, _models = select_provider(config)
        self.assertEqual(key, "sk-abc")

    def test_missing_provider_raises(self):
        config = _config({"llm": {"provider": "nope"}})
        with self.assertRaises(KeyError):
            select_provider(config)


class TestPromptRegistry(unittest.TestCase):
    def test_kinds_map_to_valid_tiers(self):
        self.assertEqual(set(PROMPTS), {"report", "epicrisis", "imaging", "lab", "pre_exam"})
        for kind, (tier, system, max_tokens) in PROMPTS.items():
            self.assertIn(tier, TIERS, f"{kind} uses unknown tier {tier}")
            self.assertTrue(system.strip(), f"{kind} has an empty prompt")
            self.assertGreater(max_tokens, 0)

    def test_tier_assignment(self):
        self.assertEqual(PROMPTS["report"][0], "default")
        self.assertEqual(PROMPTS["epicrisis"][0], "default")
        self.assertEqual(PROMPTS["imaging"][0], "medical")
        self.assertEqual(PROMPTS["lab"][0], "medical")
        self.assertEqual(PROMPTS["pre_exam"][0], "medical")


if __name__ == "__main__":
    unittest.main()
