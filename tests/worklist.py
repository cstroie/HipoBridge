#!/usr/bin/env python3
"""
Offline tests for the DICOM Modality Worklist module.

No live Hipocrate server or credentials needed — tests exercise the
local logic only (name conversion, dataset building, cache, C-FIND
matching) and one end-to-end C-ECHO/C-FIND against a locally started
SCP with a pre-seeded cache.
"""
import threading
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

try:
    from pydicom import Dataset
    from pydicom.sequence import Sequence
    from pynetdicom import AE
    from pynetdicom.sop_class import ModalityWorklistInformationFind, Verification
    DICOM_AVAILABLE = True
except ImportError:
    DICOM_AVAILABLE = False

from worklist import (
    _name_to_dicom, _build_datasets, _MODALITY_CODE,
    WorklistCache, WorklistServer, _HIPOCRATE_TO_FHIR,
)


# ---------------------------------------------------------------------------
# Name conversion
# ---------------------------------------------------------------------------

class TestNameToDicom(unittest.TestCase):

    def test_plain_name(self):
        self.assertEqual(_name_to_dicom('POPESCU ION'), 'POPESCU^ION')

    def test_dr_prefix_separate(self):
        result = _name_to_dicom('DR. IONESCU MARIA')
        self.assertEqual(result, 'IONESCU^MARIA ^^DR.')

    def test_glued_prefix(self):
        result = _name_to_dicom('DR.POPESCU ION')
        self.assertEqual(result, 'POPESCU^ION ^^DR.')

    def test_prof_dr(self):
        result = _name_to_dicom('PROF. DR. STANESCU ANA')
        self.assertIn('STANESCU', result)
        self.assertIn('ANA', result)

    def test_empty(self):
        self.assertEqual(_name_to_dicom(''), '')

    def test_no_trailing_caret_without_suffix(self):
        result = _name_to_dicom('DR. POPA ION')
        self.assertFalse(result.endswith('^'))


# ---------------------------------------------------------------------------
# Dataset building
# ---------------------------------------------------------------------------

class TestBuildDatasets(unittest.TestCase):

    def _entry(self, **kwargs):
        base = {
            'request_id':   '1721991',
            'request_code': 'ES9686',
            'patient_name': 'POPESCU ION',
            'date_time':    '2026-06-23 09:30',
            'modality':     'eco',
            'laboratory':   'Ecografie',
            'requested_by': 'DR. IONESCU MARIA',
            '_fhir_status': 'draft',
        }
        base.update(kwargs)
        return base

    def _info(self, **kwargs):
        base = {
            'id':         '421200000417490',
            'cnp':        '1850623400011',
            'name':       'POPESCU ION',
            'birth_date': '1985-06-23',
            'sex':        'M',
            'exams':      [],
        }
        base.update(kwargs)
        return base

    def test_single_exam_no_suffix(self):
        ds_list = _build_datasets(self._entry(), self._info())
        self.assertEqual(len(ds_list), 1)
        ds = ds_list[0]
        self.assertEqual(str(ds.ScheduledProcedureStepSequence[0].ScheduledProcedureStepID),
                         '1721991')

    def test_multi_exam_splits(self):
        info = self._info(exams=['ECOGRAFIE ABDOMEN', 'ECOGRAFIE PELVIS'])
        ds_list = _build_datasets(self._entry(), info)
        self.assertEqual(len(ds_list), 2)
        ids = [str(ds.ScheduledProcedureStepSequence[0].ScheduledProcedureStepID)
               for ds in ds_list]
        self.assertIn('1721991-1', ids)
        self.assertIn('1721991-2', ids)

    def test_multi_exam_descriptions(self):
        info = self._info(exams=['ECOGRAFIE ABDOMEN', 'ECOGRAFIE PELVIS'])
        ds_list = _build_datasets(self._entry(), info)
        descs = [str(ds.RequestedProcedureDescription) for ds in ds_list]
        self.assertIn('ECOGRAFIE ABDOMEN', descs)
        self.assertIn('ECOGRAFIE PELVIS', descs)

    def test_shared_accession_and_uid(self):
        info = self._info(exams=['EXAM A', 'EXAM B'])
        ds_list = _build_datasets(self._entry(), info)
        accessions = {str(ds.AccessionNumber) for ds in ds_list}
        uids = {str(ds.StudyInstanceUID) for ds in ds_list}
        self.assertEqual(len(accessions), 1)
        self.assertEqual(len(uids), 1)

    def test_accession_is_request_id(self):
        ds_list = _build_datasets(self._entry(), self._info())
        self.assertEqual(str(ds_list[0].AccessionNumber), '1721991')

    def test_accession_prefix(self):
        ds_list = _build_datasets(self._entry(), self._info(), accession_prefix='HB-')
        self.assertEqual(str(ds_list[0].AccessionNumber), 'HB-1721991')

    def test_patient_id_is_cnp(self):
        ds_list = _build_datasets(self._entry(), self._info())
        self.assertEqual(str(ds_list[0].PatientID), '1850623400011')

    def test_birth_date_from_record(self):
        ds_list = _build_datasets(self._entry(), self._info())
        self.assertEqual(str(ds_list[0].PatientBirthDate), '19850623')

    def test_birth_date_from_cnp_fallback(self):
        # CNP 1850623... → born 1985-06-23
        info = self._info(birth_date='', cnp='1850623123456')
        ds_list = _build_datasets(self._entry(), info)
        self.assertEqual(str(ds_list[0].PatientBirthDate), '19850623')

    def test_modality_code(self):
        ds_list = _build_datasets(self._entry(), self._info())
        mod = str(ds_list[0].ScheduledProcedureStepSequence[0].Modality)
        self.assertEqual(mod, 'US')

    def test_no_patient_info_fallback(self):
        ds_list = _build_datasets(self._entry(), None)
        self.assertEqual(len(ds_list), 1)
        self.assertEqual(str(ds_list[0].PatientID), '1721991')


# ---------------------------------------------------------------------------
# WorklistCache
# ---------------------------------------------------------------------------

class TestWorklistCache(unittest.TestCase):

    def _make_ds(self, accession):
        ds = Dataset()
        ds.AccessionNumber = accession
        return ds

    def test_update_and_snapshot(self):
        cache = WorklistCache()
        ds = self._make_ds('ACC1')
        cache.update('26', [ds], [{'request_id': '1'}])
        entries, raw = cache.snapshot('26')
        self.assertEqual(len(entries), 1)
        self.assertEqual(str(entries[0].AccessionNumber), 'ACC1')

    def test_independent_slots(self):
        cache = WorklistCache()
        cache.update('26', [self._make_ds('CT1')], [{'request_id': '1'}])
        cache.update('28', [self._make_ds('US1')], [{'request_id': '2'}])
        ct, _ = cache.snapshot('26')
        us, _ = cache.snapshot('28')
        self.assertEqual(str(ct[0].AccessionNumber), 'CT1')
        self.assertEqual(str(us[0].AccessionNumber), 'US1')

    def test_snapshot_none_merges_all(self):
        cache = WorklistCache()
        cache.update('26', [self._make_ds('CT1')], [{'request_id': '1'}])
        cache.update('28', [self._make_ds('US1')], [{'request_id': '2'}])
        all_ds, _ = cache.snapshot(None)
        self.assertEqual(len(all_ds), 2)

    def test_snapshot_multi(self):
        cache = WorklistCache()
        cache.update('35', [self._make_ds('IR1')], [{'request_id': '1'}])
        cache.update('50', [self._make_ds('FL1')], [{'request_id': '2'}])
        combined, _ = cache.snapshot_multi(['35', '50'])
        self.assertEqual(len(combined), 2)

    def test_update_replaces_slot(self):
        cache = WorklistCache()
        cache.update('26', [self._make_ds('OLD')], [{'request_id': '1'}])
        cache.update('26', [self._make_ds('NEW')], [{'request_id': '1'}])
        entries, _ = cache.snapshot('26')
        self.assertEqual(str(entries[0].AccessionNumber), 'NEW')


# ---------------------------------------------------------------------------
# End-to-end C-ECHO + C-FIND (requires pynetdicom)
# ---------------------------------------------------------------------------

@unittest.skipUnless(DICOM_AVAILABLE, "pynetdicom not installed")
class TestWorklistSCP(unittest.TestCase):

    PORT = 11199   # use a non-standard port so tests don't clash with production

    @classmethod
    def setUpClass(cls):
        """Start a WorklistServer with a pre-seeded cache on a test port."""
        from worklist import WorklistServer, WorklistCache

        # Build a minimal test Dataset
        ds = Dataset()
        ds.PatientName      = 'TEST^PATIENT'
        ds.PatientID        = '1234567890123'
        ds.PatientBirthDate = '19900101'
        ds.PatientSex       = 'M'
        ds.AccessionNumber  = '9999001'
        ds.ReferringPhysicianName        = 'DR^HOUSE'
        ds.RequestedProcedureDescription = 'ECOGRAFIE TEST'
        ds.RequestedProcedureID          = '9999001'
        ds.StudyInstanceUID              = '1.2.840.99999999.1.9999001'
        sps = Dataset()
        sps.ScheduledProcedureStepStartDate  = '20260623'
        sps.ScheduledProcedureStepStartTime  = '0930'
        sps.Modality                          = 'US'
        sps.ScheduledProcedureStepDescription = 'ECOGRAFIE TEST'
        sps.ScheduledProcedureStepID          = '9999001'
        sps.ScheduledStationAETitle           = ''
        sps.ScheduledPerformingPhysicianName  = ''
        ds.ScheduledProcedureStepSequence = Sequence([sps])

        cache = WorklistCache()
        cache.update('28', [ds], [{'request_id': '9999001', '_fhir_status': 'draft',
                                   'modality': 'eco', 'section': 'TEST'}])

        profiles = [{
            'name':              'TEST_SCU',
            'ae_title':          'TEST_SCU',
            'modality':          'US',
            'wards':             [],
            'time_window_hours': 0.0,
        }]
        server_cfg = {
            'ae_title':                  'TEST_SCP',
            'port':                      cls.PORT,
            'on_demand_refresh_seconds': 60.0,
        }
        cls.server = WorklistServer(cache=cache, profiles=profiles,
                                    server_cfg=server_cfg)
        cls._thread = threading.Thread(target=cls.server.serve, daemon=True)
        cls._thread.start()
        time.sleep(0.3)   # give pynetdicom time to bind

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def _scu(self):
        ae = AE(ae_title='TEST_SCU')
        ae.add_requested_context(Verification)
        ae.add_requested_context(ModalityWorklistInformationFind)
        return ae

    def test_echo(self):
        ae = self._scu()
        assoc = ae.associate('127.0.0.1', self.PORT, ae_title='TEST_SCP')
        self.assertTrue(assoc.is_established, "C-ECHO association failed")
        status = assoc.send_c_echo()
        self.assertEqual(status.Status, 0x0000)
        assoc.release()

    def test_cfind_returns_entry(self):
        ae = self._scu()
        assoc = ae.associate('127.0.0.1', self.PORT, ae_title='TEST_SCP')
        self.assertTrue(assoc.is_established)

        identifier = Dataset()
        identifier.QueryRetrieveLevel    = 'WORKLIST'
        identifier.PatientName           = ''
        identifier.PatientID             = ''
        identifier.AccessionNumber       = ''
        sps = Dataset()
        sps.ScheduledProcedureStepStartDate = ''
        sps.Modality                        = ''
        identifier.ScheduledProcedureStepSequence = Sequence([sps])

        results = list(assoc.send_c_find(identifier, ModalityWorklistInformationFind))
        assoc.release()

        pending = [(s, d) for s, d in results if s and s.Status == 0xFF00]
        self.assertGreater(len(pending), 0, "Expected at least one C-FIND result")
        self.assertEqual(str(pending[0][1].AccessionNumber), '9999001')

    def test_cfind_modality_filter(self):
        """C-FIND with Modality=CT should return nothing (cache only has US)."""
        ae = self._scu()
        assoc = ae.associate('127.0.0.1', self.PORT, ae_title='TEST_SCP')
        self.assertTrue(assoc.is_established)

        identifier = Dataset()
        identifier.QueryRetrieveLevel = 'WORKLIST'
        identifier.PatientName        = ''
        sps = Dataset()
        sps.ScheduledProcedureStepStartDate = ''
        sps.Modality                        = 'CT'
        identifier.ScheduledProcedureStepSequence = Sequence([sps])

        results = list(assoc.send_c_find(identifier, ModalityWorklistInformationFind))
        assoc.release()
        pending = [(s, d) for s, d in results if s and s.Status == 0xFF00]
        self.assertEqual(len(pending), 0)

    def test_unknown_ae_rejected(self):
        ae = AE(ae_title='INTRUDER')
        ae.add_requested_context(ModalityWorklistInformationFind)
        assoc = ae.associate('127.0.0.1', self.PORT, ae_title='TEST_SCP')
        if assoc.is_established:
            identifier = Dataset()
            identifier.QueryRetrieveLevel = 'WORKLIST'
            sps = Dataset()
            sps.ScheduledProcedureStepStartDate = ''
            sps.Modality = ''
            identifier.ScheduledProcedureStepSequence = Sequence([sps])
            results = list(assoc.send_c_find(identifier, ModalityWorklistInformationFind))
            assoc.release()
            statuses = [s.Status for s, _ in results if s]
            self.assertTrue(any(s == 0xA700 for s in statuses),
                            "Unknown AE should receive 0xA700 failure")
