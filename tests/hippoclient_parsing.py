#!/usr/bin/env python3
"""Tests for hippoclient.py's _parse_buletin_header(): the field-group
isolation and narrowed exception handling added when a single blanket
`except Exception` around the whole ~50-line function was split into one
try/except per independent field group (date/barcode, patient identity,
patient id/urgency/gender, section/medic, clinical indication)."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from bs4 import BeautifulSoup

import hippoclient
from hippodata import HippoData
from hippoclient import _parse_buletin_header


def _make_soup():
    html = (
        '<table>'
        '<tr><td>ignored</td></tr>'
        '<tr><td>x</td><td>Nr.Reg.1 Cod cerere:ABC123</td></tr>'
        '<tr>'
        '<td>NUME:POPESCU ION CNP:1850615123456</td>'
        '<td>COD PACIENT:99887766Urgenta:DASEX:M</td>'
        '<td>SECTIE:CHIRURGIEMEDIC:DR. IONESCU</td>'
        '</tr>'
        '</table>'
        '<p class="NoteSubsol">INFO SUPLIMENTAR: durere abdominala</p>'
    )
    return BeautifulSoup(html, 'html.parser')


class TestParseBuletinHeader(unittest.TestCase):
    def test_happy_path_populates_all_fields(self):
        data = HippoData()
        _parse_buletin_header(_make_soup(), data)
        self.assertEqual(data.get("request.barcode"), "ABC123")
        self.assertEqual(data.get("patient.name"), "POPESCU ION")
        self.assertEqual(data.get("patient.cnp"), "1850615123456")
        self.assertEqual(data.get("patient.id"), "99887766")
        self.assertTrue(data.get("request.is_urgent"))
        self.assertEqual(data.get("patient.gender"), "male")
        self.assertEqual(data.get("request.section"), "CHIRURGIE")
        self.assertEqual(data.get("checkin.medic"), "DR. IONESCU")
        self.assertEqual(data.get("request.clinical_comments"), "durere abdominala")

    def test_too_few_rows_is_a_noop(self):
        soup = BeautifulSoup('<table><tr><td>only one row</td></tr></table>', 'html.parser')
        data = HippoData()
        _parse_buletin_header(soup, data)
        self.assertIsNone(data.get("patient.name"))

    def test_one_field_group_failure_does_not_wipe_others(self):
        # Regression guard: before the refactor, a single blanket
        # `except Exception` around the whole function meant any failure —
        # even one confined to, say, the "cell1" (id/urgency/gender) group —
        # discarded already-extracted fields like patient name/CNP too.
        data = HippoData()
        orig_search = hippoclient.re.search

        def flaky_search(pattern, *a, **kw):
            if pattern == r'COD PACIENT:(\d+)':
                raise AttributeError("simulated malformed cell1")
            return orig_search(pattern, *a, **kw)

        hippoclient.re.search = flaky_search
        try:
            _parse_buletin_header(_make_soup(), data)
        finally:
            hippoclient.re.search = orig_search

        # cell0 group (name/CNP) and cell2 group (section) still populated.
        self.assertEqual(data.get("patient.name"), "POPESCU ION")
        self.assertEqual(data.get("patient.cnp"), "1850615123456")
        self.assertEqual(data.get("request.section"), "CHIRURGIE")
        # cell1 group (id) is the one that failed — left unset, not crashed.
        self.assertIsNone(data.get("patient.id"))

    def test_unexpected_exception_type_propagates_instead_of_being_swallowed(self):
        # Regression guard: only IndexError/AttributeError/TypeError (the
        # realistic "unexpected HTML shape" failures) are caught. Anything
        # else — e.g. a bug introduced by a future edit — must propagate
        # so it gets noticed instead of vanishing into a warning log line.
        orig_parse_cnp = hippoclient.parse_cnp

        def boom(cnp):
            raise ZeroDivisionError("simulated unexpected bug")

        hippoclient.parse_cnp = boom
        try:
            with self.assertRaises(ZeroDivisionError):
                _parse_buletin_header(_make_soup(), HippoData())
        finally:
            hippoclient.parse_cnp = orig_parse_cnp


if __name__ == "__main__":
    unittest.main()
