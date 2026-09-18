#!/usr/bin/env python3
"""Regression tests for HippoClientTriage's resolution chain (cerere.asp ->
patient page -> most recent FUPU.asp) and its business rules: only UPU
(ER) sections carry triage data, and the most recent presentation is the
one with the highest numeric id.

Mocks at the sub-client fetch_and_parse() level (HippoClientCerere,
HippoClientPatient, HippoClientFUPU) rather than raw HTML, since the
behavior under test is HippoClientTriage's own orchestration/business
logic, not any one page's parsing.

Plain (synchronous) unittest.TestCase driven through _run(), same pattern
as tests/hippoclient_write.py — see that module's docstring for why not
IsolatedAsyncioTestCase.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, patch

from hippoclient import HippoClientTriage, HippoClientCerere, HippoClientPatient, HippoClientFUPU
from hippodata import HippoData


def _run(coro):
    """Run coro to completion on a fresh event loop in a separate thread."""
    with ThreadPoolExecutor(1) as ex:
        return ex.submit(asyncio.run, coro).result()


def _client():
    c = HippoClientTriage("http://test.invalid", None)
    c.set_credentials("user", "pass")
    return c


def _cerere_data(section=None, patient_id=None, status="success"):
    data = HippoData(status=status, message="")
    if section is not None:
        data.store("request.section", section)
    if patient_id is not None:
        data.store("patient.id", patient_id)
    return data


def _patient_data(presentation=None):
    data = HippoData(status="success", message="")
    if presentation is not None:
        data.store("presentation", presentation)
    return data


def _fupu_data(priority=None, code=None, status="success", **extra_fields):
    data = HippoData(status=status, message="")
    if priority is not None:
        data.store("fupu.triage_priority", priority)
    if code is not None:
        data.store("fupu.triage_priority_code", code)
    for key, value in extra_fields.items():
        data.store(f"fupu.{key}", value)
    return data


class TestTriageResolution(unittest.TestCase):
    def test_non_upu_section_skips_patient_and_fupu_lookup(self):
        with patch.object(HippoClientCerere, 'fetch_and_parse',
                           AsyncMock(return_value=_cerere_data(section='Radiologie', patient_id='P1'))), \
             patch.object(HippoClientPatient, 'fetch_and_parse', AsyncMock()) as patient_mock, \
             patch.object(HippoClientFUPU, 'fetch_and_parse', AsyncMock()) as fupu_mock:
            data = _run(_client().fetch_and_parse(id='111'))
        self.assertEqual(data.get('status'), 'success')
        self.assertIsNone(data.get('triage_priority'))
        self.assertIsNone(data.get('triage_priority_code'))
        self.assertIsNone(data.get('presentation_reason'))
        patient_mock.assert_not_called()
        fupu_mock.assert_not_called()

    def test_section_comparison_is_case_and_whitespace_insensitive(self):
        with patch.object(HippoClientCerere, 'fetch_and_parse',
                           AsyncMock(return_value=_cerere_data(section=' upu ', patient_id='P1'))), \
             patch.object(HippoClientPatient, 'fetch_and_parse',
                           AsyncMock(return_value=_patient_data(presentation=None))) as patient_mock:
            data = _run(_client().fetch_and_parse(id='111'))
        patient_mock.assert_called_once()
        self.assertIsNone(data.get('triage_priority'))

    def test_cerere_error_is_propagated_as_is(self):
        error_data = _cerere_data(status='error')
        error_data.set_error("Nu aveti suficiente drepturi")
        with patch.object(HippoClientCerere, 'fetch_and_parse', AsyncMock(return_value=error_data)):
            data = _run(_client().fetch_and_parse(id='111'))
        self.assertEqual(data.get('status'), 'error')
        self.assertEqual(data.get('message'), "Nu aveti suficiente drepturi")

    def test_upu_without_patient_id_returns_nulls(self):
        with patch.object(HippoClientCerere, 'fetch_and_parse',
                           AsyncMock(return_value=_cerere_data(section='UPU', patient_id=None))), \
             patch.object(HippoClientPatient, 'fetch_and_parse', AsyncMock()) as patient_mock:
            data = _run(_client().fetch_and_parse(id='111'))
        self.assertEqual(data.get('status'), 'success')
        self.assertIsNone(data.get('triage_priority'))
        patient_mock.assert_not_called()

    def test_no_presentation_ids_returns_nulls(self):
        with patch.object(HippoClientCerere, 'fetch_and_parse',
                           AsyncMock(return_value=_cerere_data(section='UPU', patient_id='P1'))), \
             patch.object(HippoClientPatient, 'fetch_and_parse',
                           AsyncMock(return_value=_patient_data(presentation=None))), \
             patch.object(HippoClientFUPU, 'fetch_and_parse', AsyncMock()) as fupu_mock:
            data = _run(_client().fetch_and_parse(id='111'))
        self.assertIsNone(data.get('triage_priority'))
        fupu_mock.assert_not_called()

    def test_single_presentation_id_not_wrapped_in_list_is_used_directly(self):
        with patch.object(HippoClientCerere, 'fetch_and_parse',
                           AsyncMock(return_value=_cerere_data(section='UPU', patient_id='P1'))), \
             patch.object(HippoClientPatient, 'fetch_and_parse',
                           AsyncMock(return_value=_patient_data(presentation='555'))), \
             patch.object(HippoClientFUPU, 'fetch_and_parse',
                           AsyncMock(return_value=_fupu_data(priority='Urgent', code='32'))) as fupu_mock:
            data = _run(_client().fetch_and_parse(id='111'))
        fupu_mock.assert_called_once_with(id='555')
        self.assertEqual(data.get('triage_priority'), 'Urgent')
        self.assertEqual(data.get('triage_priority_code'), '32')

    def test_most_recent_presentation_picked_by_highest_numeric_id(self):
        with patch.object(HippoClientCerere, 'fetch_and_parse',
                           AsyncMock(return_value=_cerere_data(section='UPU', patient_id='P1'))), \
             patch.object(HippoClientPatient, 'fetch_and_parse',
                           AsyncMock(return_value=_patient_data(presentation=['20', '100', '3']))), \
             patch.object(HippoClientFUPU, 'fetch_and_parse',
                           AsyncMock(return_value=_fupu_data(priority='Critical', code='31'))) as fupu_mock:
            data = _run(_client().fetch_and_parse(id='111'))
        fupu_mock.assert_called_once_with(id='100')
        self.assertEqual(data.get('triage_priority'), 'Critical')

    def test_fupu_fetch_error_returns_nulls_not_error(self):
        error_fupu = _fupu_data(status='error')
        error_fupu.set_error("FUPU not found")
        with patch.object(HippoClientCerere, 'fetch_and_parse',
                           AsyncMock(return_value=_cerere_data(section='UPU', patient_id='P1'))), \
             patch.object(HippoClientPatient, 'fetch_and_parse',
                           AsyncMock(return_value=_patient_data(presentation=['7']))), \
             patch.object(HippoClientFUPU, 'fetch_and_parse', AsyncMock(return_value=error_fupu)):
            data = _run(_client().fetch_and_parse(id='111'))
        self.assertEqual(data.get('status'), 'success')
        self.assertIsNone(data.get('triage_priority'))

    def test_full_fupu_fields_are_passed_through_flattened(self):
        """er_triage's prompt input needs more than the priority badge —
        record_number/date/arrival_mode/arrival_source/presentation_reason
        must all come through under their flat (non-fupu.-prefixed) names."""
        with patch.object(HippoClientCerere, 'fetch_and_parse',
                           AsyncMock(return_value=_cerere_data(section='UPU', patient_id='P1'))), \
             patch.object(HippoClientPatient, 'fetch_and_parse',
                           AsyncMock(return_value=_patient_data(presentation='555'))), \
             patch.object(HippoClientFUPU, 'fetch_and_parse',
                           AsyncMock(return_value=_fupu_data(
                               priority='Urgent', code='32',
                               record_number='12345', date='2026-09-15',
                               arrival_mode='Ambulance', arrival_source='Home',
                               presentation_reason='Sudden abdominal pain'))):
            data = _run(_client().fetch_and_parse(id='111'))
        self.assertEqual(data.get('triage_priority'), 'Urgent')
        self.assertEqual(data.get('triage_priority_code'), '32')
        self.assertEqual(data.get('record_number'), '12345')
        self.assertEqual(data.get('date'), '2026-09-15')
        self.assertEqual(data.get('arrival_mode'), 'Ambulance')
        self.assertEqual(data.get('arrival_source'), 'Home')
        self.assertEqual(data.get('presentation_reason'), 'Sudden abdominal pain')

    def test_non_numeric_presentation_id_degrades_instead_of_raising(self):
        """The edge case this class previously had no guard against: a
        malformed/non-numeric presentation id must not raise ValueError out
        of fetch_and_parse — it should degrade like every other
        missing-data branch (see the try/except around max() in
        hippoclient.py)."""
        with patch.object(HippoClientCerere, 'fetch_and_parse',
                           AsyncMock(return_value=_cerere_data(section='UPU', patient_id='P1'))), \
             patch.object(HippoClientPatient, 'fetch_and_parse',
                           AsyncMock(return_value=_patient_data(presentation=['12', 'not-a-number']))), \
             patch.object(HippoClientFUPU, 'fetch_and_parse', AsyncMock()) as fupu_mock:
            data = _run(_client().fetch_and_parse(id='111'))
        self.assertEqual(data.get('status'), 'success')
        self.assertIsNone(data.get('triage_priority'))
        self.assertIsNone(data.get('triage_priority_code'))
        fupu_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
