#!/usr/bin/env python3
"""
Offline tests for the PACS study-check module (pacs.py).

No live PACS or Hipocrate server needed — tests exercise the local logic
only (config parsing, CNP pre-filter, identifier construction, C-FIND
result classification).
"""
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

try:
    from pydicom import Dataset
    DICOM_AVAILABLE = True
except ImportError:
    DICOM_AVAILABLE = False

from pacs import _load_config, PacsChecker
from hippobridge import load_config as hb_load_config, DEFAULT_CONFIG


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------

class TestLoadConfig(unittest.TestCase):

    def _config(self, content):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        path = os.path.join(d.name, 'hippobridge.cfg')
        with open(path, 'w') as f:
            f.write(content)
        return hb_load_config(path)

    def test_defaults_when_section_absent(self):
        config = self._config("[server]\nport = 8080\n")
        cfg = _load_config(config)
        self.assertEqual(cfg['host'], '')
        self.assertEqual(cfg['port'], 104)
        self.assertEqual(cfg['calling_ae_title'], 'HIPPOBRIDGE')
        self.assertEqual(cfg['poll_interval_seconds'], 600)
        self.assertEqual(cfg['cold_start_lookback_hours'], 8)

    def test_section_overrides(self):
        config = self._config(
            "[pacs]\n"
            "host = 192.168.3.50\n"
            "port = 104\n"
            "called_ae_title = 3DNETCLOUD\n"
            "calling_ae_title = MYAE\n"
            "poll_interval_seconds = 120\n"
            "cold_start_lookback_hours = 4\n"
            "username = alice\n"
            "password = secret\n"
        )
        cfg = _load_config(config)
        self.assertEqual(cfg['host'], '192.168.3.50')
        self.assertEqual(cfg['called_ae_title'], '3DNETCLOUD')
        self.assertEqual(cfg['calling_ae_title'], 'MYAE')
        self.assertEqual(cfg['poll_interval_seconds'], 120)
        self.assertEqual(cfg['cold_start_lookback_hours'], 4)
        self.assertEqual(cfg['username'], 'alice')
        self.assertEqual(cfg['password'], 'secret')

    @patch.dict(os.environ, {'HYP_USER': 'envuser', 'HYP_PASS': 'envpass'})
    def test_credentials_fall_back_to_environment(self):
        config = self._config("[pacs]\nhost = 192.168.3.50\n")
        cfg = _load_config(config)
        self.assertEqual(cfg['username'], 'envuser')
        self.assertEqual(cfg['password'], 'envpass')

    def test_default_config_dict_has_pacs_section(self):
        # Regression guard: hippobridge.DEFAULT_CONFIG must carry [pacs]
        # defaults, or load_config() would raise on config.get('pacs', ...).
        self.assertIn('pacs', DEFAULT_CONFIG)
        self.assertEqual(DEFAULT_CONFIG['pacs']['host'], '')


# ---------------------------------------------------------------------------
# CNP pre-filter (never put unvalidated input on the wire as PatientID)
# ---------------------------------------------------------------------------

class TestCnpPreFilter(unittest.TestCase):

    def test_rejects_malformed_cnp(self):
        from extractors import parse_cnp
        self.assertFalse(parse_cnp('not-a-cnp').get('valid'))
        self.assertFalse(parse_cnp('').get('valid'))
        self.assertFalse(parse_cnp('123').get('valid'))


# ---------------------------------------------------------------------------
# Identifier construction / result classification (DICOM-dependent)
# ---------------------------------------------------------------------------

@unittest.skipUnless(DICOM_AVAILABLE, "pynetdicom/pydicom not installed")
class TestBuildIdentifier(unittest.TestCase):

    def test_fields(self):
        since = datetime(2026, 8, 20, 9, 0)
        until = datetime(2026, 8, 25, 17, 0)
        ds = PacsChecker._build_identifier('1234567890123', 'CT', since, until)
        self.assertEqual(ds.QueryRetrieveLevel, 'STUDY')
        self.assertEqual(ds.PatientID, '1234567890123')
        self.assertEqual(ds.StudyDate, '20260820-20260825')
        self.assertEqual(ds.ModalitiesInStudy, 'CT')
        self.assertEqual(ds.NumberOfStudyRelatedInstances, '')


@unittest.skipUnless(DICOM_AVAILABLE, "pynetdicom/pydicom not installed")
class TestClassify(unittest.TestCase):

    def test_performed_when_instances_positive(self):
        ds = Dataset()
        ds.ModalitiesInStudy = 'CR'
        ds.NumberOfStudyRelatedInstances = '42'
        ds.StudyDate = '20260825'
        outcome, detail = PacsChecker._classify(ds, 'CR')
        self.assertEqual(outcome, 'performed')
        self.assertEqual(detail['instances'], 42)
        self.assertEqual(detail['study_date'], '20260825')

    def test_not_found_when_instances_zero(self):
        ds = Dataset()
        ds.ModalitiesInStudy = 'CR'
        ds.NumberOfStudyRelatedInstances = '0'
        outcome, _detail = PacsChecker._classify(ds, 'CR')
        self.assertEqual(outcome, 'not_found')

    def test_likely_when_instance_count_absent(self):
        ds = Dataset()
        ds.ModalitiesInStudy = 'CR'
        # NumberOfStudyRelatedInstances intentionally not set — some PACS
        # never return this optional key.
        outcome, detail = PacsChecker._classify(ds, 'CR')
        self.assertEqual(outcome, 'likely')
        self.assertIsNone(detail['instances'])

    def test_likely_when_instance_count_blank(self):
        ds = Dataset()
        ds.ModalitiesInStudy = 'CR'
        ds.NumberOfStudyRelatedInstances = ''
        outcome, detail = PacsChecker._classify(ds, 'CR')
        self.assertEqual(outcome, 'likely')
        self.assertIsNone(detail['instances'])

    def test_not_found_when_modality_absent_from_single_value(self):
        # A PACS that ignores our ModalitiesInStudy matching key and returns
        # a study of an unrelated modality must not be trusted as "performed"
        # for the modality we actually asked about.
        ds = Dataset()
        ds.ModalitiesInStudy = 'CT'
        ds.NumberOfStudyRelatedInstances = '10'
        outcome, detail = PacsChecker._classify(ds, 'US')
        self.assertEqual(outcome, 'not_found')
        self.assertEqual(detail['modalities_in_study'], ['CT'])

    def test_not_found_when_modality_absent_from_multi_value(self):
        # A study can legitimately carry several modalities (e.g. an image
        # series plus its structured report, ['CR', 'SR']) — only count it
        # if the requested modality is actually one of them.
        ds = Dataset()
        ds.ModalitiesInStudy = ['CT', 'SR']
        ds.NumberOfStudyRelatedInstances = '784'
        outcome, detail = PacsChecker._classify(ds, 'US')
        self.assertEqual(outcome, 'not_found')
        self.assertEqual(detail['modalities_in_study'], ['CT', 'SR'])

    def test_performed_when_requested_modality_among_several(self):
        ds = Dataset()
        ds.ModalitiesInStudy = ['CR', 'SR']
        ds.NumberOfStudyRelatedInstances = '14'
        outcome, detail = PacsChecker._classify(ds, 'CR')
        self.assertEqual(outcome, 'performed')
        self.assertEqual(detail['instances'], 14)

    def test_no_cross_check_when_modalities_in_study_absent(self):
        # Some PACS don't echo ModalitiesInStudy back at all — fall back to
        # trusting the outbound query filter alone in that case.
        ds = Dataset()
        ds.NumberOfStudyRelatedInstances = '5'
        outcome, _detail = PacsChecker._classify(ds, 'US')
        self.assertEqual(outcome, 'performed')


if __name__ == '__main__':
    unittest.main()
