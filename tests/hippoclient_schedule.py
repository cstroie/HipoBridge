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


class TestTranslation(unittest.TestCase):
    """Hipocrate's Romanian status/priority/payment text → standard values."""
    C = HippoClientSchedule

    def test_status(self):
        self.assertEqual(self.C._fhir_status('Cerere Completata', False), 'completed')
        self.assertEqual(self.C._fhir_status('Terminata', True), 'ended')
        self.assertEqual(self.C._fhir_status('x', False), 'unknown')

    def test_performed_promotes_sent_to_lab_to_active(self):
        self.assertEqual(self.C._fhir_status('Trimisa in laborator', False), 'draft')
        self.assertEqual(self.C._fhir_status('Trimisa in laborator', True), 'active')

    def test_priority(self):
        self.assertEqual(self.C._priority('Urgenta'), 'urgent')
        self.assertEqual(self.C._priority('Normala'), 'routine')
        self.assertEqual(self.C._priority(''), 'routine')

    def test_payment(self):
        self.assertEqual(self.C._payment_slug('Spitalizare de zi'), 'day-care')
        self.assertEqual(self.C._payment_slug('Urgenta'), 'emergency')
        self.assertEqual(self.C._payment_slug('???'), 'other')
        self.assertEqual(self.C._payment_slug(''), '')

    def test_status_filter_uses_translated_status(self):
        c = HippoClientSchedule("http://test.invalid", None)
        rows = [{'status': 'draft'}, {'status': 'ended'}, {'status': 'active'}]
        self.assertEqual([r['status'] for r in c._apply_filters(rows, status='draft,active')],
                         ['draft', 'active'])


class TestFhirBundle(unittest.TestCase):
    def test_uses_translated_row_values(self):
        c = HippoClientSchedule("http://test.invalid", None)
        from hippodata import HippoData
        d = HippoData(status="success", message="")
        d.store_list("requests", [{'request_id': '1', 'status': 'ended', 'priority': 'urgent',
                                   'payment_type': 'day-care', 'laboratory': 'MRI', 'modality': 'irm'}])
        text = str(c.fhir_response(d).to_dict())
        self.assertIn("'ended'", text)
        self.assertIn("'urgent'", text)
        self.assertIn("'day-care'", text)
        self.assertIn("Day case", text)


if __name__ == "__main__":
    unittest.main()
