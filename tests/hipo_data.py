#!/usr/bin/env python3
"""Tests for the HippoData class."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from datetime import datetime
from hippodata import HippoData


class TestHippoData(unittest.TestCase):

    def setUp(self):
        self.data = HippoData()

    # ------------------------------------------------------------------
    # Basic construction
    # ------------------------------------------------------------------

    def test_init_empty(self):
        self.assertIsInstance(self.data, dict)
        self.assertEqual(len(self.data), 0)

    def test_init_with_kwargs_normalised(self):
        """__init__ routes kwargs through store() so values are normalised."""
        d = HippoData(name="  Alice  ", score=None)
        self.assertEqual(d["name"], "Alice")       # stripped
        self.assertNotIn("score", d)               # None skipped

    def test_init_status_success_no_message(self):
        """status='success' with no message stores only status."""
        d = HippoData(status="success")
        self.assertEqual(d["status"], "success")
        self.assertNotIn("message", d)

    # ------------------------------------------------------------------
    # store() — root keys
    # ------------------------------------------------------------------

    def test_store_root_string(self):
        self.data.store("name", "John Doe")
        self.assertEqual(self.data["name"], "John Doe")

    def test_store_root_strips_string(self):
        self.data.store("name", "  John Doe  ")
        self.assertEqual(self.data["name"], "John Doe")

    def test_store_root_skips_none(self):
        self.data.store("name", None)
        self.assertNotIn("name", self.data)

    def test_store_root_empty_string_is_stored(self):
        """Empty string is not None — it is stored as-is."""
        self.data.store("name", "")
        self.assertEqual(self.data["name"], "")

    def test_store_root_overwrites(self):
        self.data.store("name", "John")
        self.data.store("name", "Jane")
        self.assertEqual(self.data["name"], "Jane")

    def test_store_unwraps_single_element_list(self):
        self.data.store("id", ["12345"])
        self.assertEqual(self.data["id"], "12345")
        self.assertNotIsInstance(self.data["id"], list)

    def test_store_keeps_multi_element_list(self):
        self.data.store("ids", ["a", "b"])
        self.assertEqual(self.data["ids"], ["a", "b"])

    def test_store_converts_datetime_to_iso(self):
        dt = datetime(2025, 3, 15, 10, 30, 0)
        self.data.store("dt", dt)
        self.assertEqual(self.data["dt"], "2025-03-15T10:30:00")

    # ------------------------------------------------------------------
    # store() — dot-notation
    # ------------------------------------------------------------------

    def test_store_section_key(self):
        self.data.store("patient.id", "12345")
        self.assertIsInstance(self.data["patient"], dict)
        self.assertEqual(self.data["patient"]["id"], "12345")

    def test_store_multiple_keys_same_section(self):
        self.data.store("patient.id", "12345")
        self.data.store("patient.name", "John Doe")
        self.assertEqual(self.data["patient"]["id"], "12345")
        self.assertEqual(self.data["patient"]["name"], "John Doe")

    def test_store_dot_skips_none(self):
        self.data.store("patient.name", None)
        self.assertNotIn("patient", self.data)

    def test_store_dot_empty_subkey_ignored(self):
        self.data.store("patient.", "value")
        self.assertNotIn("patient", self.data)

    def test_store_promotes_scalar_to_dict(self):
        """If section already holds a scalar, promote it to {"": scalar}."""
        self.data.store("patient", "original")
        self.data.store("patient.id", "123")
        self.assertEqual(self.data["patient"]["id"], "123")
        self.assertEqual(self.data["patient"][""], "original")

    # ------------------------------------------------------------------
    # store_list()
    # ------------------------------------------------------------------

    def test_store_list_wraps_scalar(self):
        self.data.store_list("ids", "abc")
        self.assertEqual(self.data["ids"], ["abc"])

    def test_store_list_keeps_list(self):
        self.data.store_list("ids", ["a", "b"])
        self.assertEqual(self.data["ids"], ["a", "b"])

    def test_store_list_skips_none(self):
        self.data.store_list("ids", None)
        self.assertNotIn("ids", self.data)

    def test_store_list_dot_notation(self):
        self.data.store_list("patient.ids", ["p1", "p2"])
        self.assertEqual(self.data["patient"]["ids"], ["p1", "p2"])

    # ------------------------------------------------------------------
    # get()
    # ------------------------------------------------------------------

    def test_get_existing_section_key(self):
        self.data.store("patient.name", "John Doe")
        self.assertEqual(self.data.get("patient.name"), "John Doe")

    def test_get_missing_returns_none_by_default(self):
        """Default is None, matching dict.get() behaviour."""
        self.assertIsNone(self.data.get("patient.name"))
        self.assertIsNone(self.data.get("missing"))

    def test_get_explicit_default(self):
        self.assertEqual(self.data.get("patient.name", "Unknown"), "Unknown")
        self.assertEqual(self.data.get("missing", ""), "")

    def test_get_root_key(self):
        self.data.store("status", "ok")
        self.assertEqual(self.data.get("status"), "ok")

    def test_get_root_key_missing(self):
        self.assertIsNone(self.data.get("status"))

    # ------------------------------------------------------------------
    # set()
    # ------------------------------------------------------------------

    def test_set_section_key(self):
        self.data.set("patient.name", "John Doe")
        self.assertEqual(self.data["patient"]["name"], "John Doe")

    def test_set_normalises_string(self):
        self.data.set("patient.name", "  Alice  ")
        self.assertEqual(self.data["patient"]["name"], "Alice")

    def test_set_normalises_datetime(self):
        dt = datetime(2025, 1, 1, 0, 0, 0)
        self.data.set("study.date", dt)
        self.assertEqual(self.data["study"]["date"], "2025-01-01T00:00:00")

    def test_set_root_key(self):
        self.data.set("status", "ok")
        self.assertEqual(self.data["status"], "ok")

    def test_set_overwrites(self):
        self.data.set("patient.name", "John")
        self.data.set("patient.name", "Jane")
        self.assertEqual(self.data["patient"]["name"], "Jane")

    # ------------------------------------------------------------------
    # set_error / set_success
    # ------------------------------------------------------------------

    def test_set_error(self):
        self.data.set_error("something broke")
        self.assertEqual(self.data["status"], "error")
        self.assertEqual(self.data["message"], "something broke")

    def test_set_success_removes_message(self):
        self.data.set_error("oops")
        self.data.set_success()
        self.assertEqual(self.data["status"], "success")
        self.assertNotIn("message", self.data)

    # ------------------------------------------------------------------
    # Complex scenario
    # ------------------------------------------------------------------

    def test_complex_scenario(self):
        self.data.store("report_id", "R001")
        self.data.store("patient.id", ["P001"])   # unwrapped
        self.data.store("patient.name", "  John Doe  ")  # stripped
        self.data.store("diagnosis", "Healthy")
        self.data.store("test.glucose", "90 mg/dL")
        self.data.store_list("test.results", ["r1", "r2"])

        self.assertEqual(self.data["report_id"], "R001")
        self.assertEqual(self.data["patient"]["id"], "P001")
        self.assertEqual(self.data["patient"]["name"], "John Doe")
        self.assertEqual(self.data["diagnosis"], "Healthy")
        self.assertEqual(self.data["test"]["glucose"], "90 mg/dL")
        self.assertEqual(self.data["test"]["results"], ["r1", "r2"])


if __name__ == '__main__':
    unittest.main()
