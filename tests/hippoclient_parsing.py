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
from hippoclient import (_parse_buletin_header, is_meaningful_text,
                         HippoClientBuletinSolicitare, HippoClientCerere)


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


class TestIsMeaningfulText(unittest.TestCase):
    """Regression guard for junk clinical-indication values that were
    slipping through as "meaningful" (e.g. request #1761786's clinical
    info of just 'A'), since is_meaningful_text() is the sole gate for
    worklist DICOM fields, FHIR clinical-indication notes, and prior-
    imaging text filtering."""

    def test_rejects_empty_and_none(self):
        self.assertFalse(is_meaningful_text(None))
        self.assertFalse(is_meaningful_text(""))
        self.assertFalse(is_meaningful_text("   "))

    def test_rejects_single_character(self):
        self.assertFalse(is_meaningful_text("A"))
        self.assertFalse(is_meaningful_text("."))

    def test_rejects_too_short(self):
        self.assertFalse(is_meaningful_text("AB"))

    def test_rejects_punctuation_only(self):
        self.assertFalse(is_meaningful_text(". .. ."))

    def test_rejects_repeated_character_run(self):
        self.assertFalse(is_meaningful_text("aaaaaaa"))
        self.assertFalse(is_meaningful_text("----"))

    def test_rejects_single_char_with_separators(self):
        self.assertFalse(is_meaningful_text("a.a.a.a"))
        self.assertFalse(is_meaningful_text("A A A"))

    def test_rejects_known_placeholder_tokens(self):
        for token in ("na", "N/A", "nu", "test", "xxx"):
            self.assertFalse(is_meaningful_text(token), token)

    def test_accepts_real_clinical_text(self):
        self.assertTrue(is_meaningful_text("Durere abdominala"))
        self.assertTrue(is_meaningful_text("R10.4"))
        self.assertTrue(is_meaningful_text("TCC"))


class TestSolicitareEmptyForm(unittest.TestCase):
    """BuletinSolicitare pages with a header but an empty body (cerere 1763334)
    are a success with no solicitation data, not an error."""

    HTML = (
        '<html><head><title>HIPOCRATE - FISA DE SOLICITARE</title></head><body>'
        '<table><thead><tr><td><table class="TabelAntet"><tr><td>'
        '<p class="Antet"><b>Departamentul: </b>UPU<br></p></td><td>'
        '<p class="Antet">Cod: <b>EY3022</b> Nr.: <b>1763334</b></p></td></tr>'
        '</table></td></tr></thead><tbody><tr><td></td></tr></tbody></table>'
        '</body></html>'
    )

    def test_missing_table_is_success_with_header_fields(self):
        data = HippoClientBuletinSolicitare().parse_data(self.HTML, id='1763334')
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data.get("request.id"), "1763334")
        self.assertEqual(data.get("request.section"), "UPU")
        self.assertEqual(data.get("request.code"), "EY3022")
        self.assertFalse(data.get("request.justification"))

    def test_wrong_page_is_still_an_error(self):
        data = HippoClientBuletinSolicitare().parse_data(
            '<html><head><title>Other</title></head></html>', id='1')
        self.assertEqual(data.get("status"), "error")


class TestCerereRecentStrip(unittest.TestCase):
    """cerere.asp's default recent-requests link strip -> request.previous."""

    HTML = (
        '<html><head><title>Cerere</title></head><body>'
        '<input name="strPacientId" value="1">'
        '<a style="color:#007399;" href="Cerere.asp?id=1762217"><b>EY1905</b>-19/09</a>'
        '<a style="color:red!important;" href="Cerere.asp?id=1762242"><b>EY1930</b>-19/09*</a>'
        '<a style="background-color:#d9fad7;color:#444;" href="Cerere.asp?id=1763270">'
        '<b>EY2958</b>-21/09</a>'
        '<a href="/Hipocrate/pacient/analysesALL.asp?type=PA&amp;pacid=1">Istoric</a>'
        '</body></html>'
    )

    def test_entries_parsed_with_current_and_flagged(self):
        data = HippoClientCerere().parse_data(self.HTML, id='1763270')
        prev = data.get("request.previous")
        self.assertEqual([e['id'] for e in prev], ['1762217', '1762242', '1763270'])
        self.assertEqual(prev[1]['code'], 'EY1930')
        self.assertEqual(prev[1]['day_month'], '19/09')
        self.assertEqual([e['flagged'] for e in prev], [False, True, False])
        self.assertEqual([e['current'] for e in prev], [False, False, True])

    def test_no_strip_leaves_field_unset(self):
        data = HippoClientCerere().parse_data(
            '<html><head><title>Cerere</title></head><body>'
            '<input name="strPacientId" value="1"></body></html>', id='1')
        self.assertFalse(data.get("request.previous"))


if __name__ == "__main__":
    unittest.main()
