#!/usr/bin/env python3
"""PACS "study performed" checker (DICOM Query/Retrieve SCU).

Periodically checks whether currently-scheduled imaging patients already
have a study in the external PACS, by C-FIND at STUDY level keyed on
PatientID = CNP (not AccessionNumber — many modalities never go through
hippobridge's own MWL/MPPS, so accession numbers don't reliably line up
across all devices; CNP is the one identifier every device and every
Hipocrate record share).

This is a signal independent of Hipocrate's own "performed_at" (Data
Efectuarii) field, which is only ever set when staff manually mark it —
some devices never trigger that. If images landed in the PACS, the exam
happened, regardless of whether Hipocrate's own status was ever updated.

Configuration: the [pacs] section of hippobridge.cfg (not a separate file —
this subsystem has exactly one PACS to talk to, unlike worklist.cfg's
per-device profiles).

Copyright (C) 2026 Costin Stroie <costinstroie@eridu.eu.org>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import asyncio
import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

try:
    from pydicom import Dataset
    from pynetdicom import AE
    from pynetdicom.sop_class import Verification, StudyRootQueryRetrieveInformationModelFind
    DICOM_AVAILABLE = True
except ImportError:
    DICOM_AVAILABLE = False

from worklist import WorklistRefresher, WorklistCache, _MODALITY_CODE
from extractors import parse_cnp

logger = logging.getLogger('Pacs')

_ENV_USER_KEYS = ('HYP_USER',)
_ENV_PASS_KEYS = ('HYP_PASS',)

# Confidence ranking used when a single query returns multiple matching
# studies — the strongest classification found wins (see _query_pacs_sync).
_OUTCOME_RANK = {'not_found': 0, 'error': 0, 'likely': 1, 'performed': 2}


def _load_config(config) -> dict:
    """Read the [pacs] section of the already-parsed hippobridge.cfg.

    config is a configparser.ConfigParser with DEFAULT_CONFIG['pacs']
    defaults already merged in by hippobridge.load_config().
    """
    username = config.get('pacs', 'username').strip() or os.environ.get('HYP_USER', '')
    password = config.get('pacs', 'password').strip() or os.environ.get('HYP_PASS', '')
    return {
        'host':                      config.get('pacs', 'host').strip(),
        'port':                      config.getint('pacs', 'port'),
        'called_ae_title':           config.get('pacs', 'called_ae_title').strip(),
        'calling_ae_title':          config.get('pacs', 'calling_ae_title').strip(),
        'poll_interval_seconds':     config.getint('pacs', 'poll_interval_seconds'),
        'cold_start_lookback_hours': config.getint('pacs', 'cold_start_lookback_hours'),
        'max_queries_per_cycle':     config.getint('pacs', 'max_queries_per_cycle'),
        'acse_timeout':              config.getint('pacs', 'acse_timeout'),
        'network_timeout':           config.getint('pacs', 'network_timeout'),
        'dimse_timeout':             config.getint('pacs', 'dimse_timeout'),
        'username':                  username,
        'password':                  password,
    }


class PacsChecker:
    """Background asyncio task: periodically checks the PACS for scheduled
    patients' studies. Owns its own WorklistRefresher, fully independent of
    worklist.py's MWL SCP — the whole point is covering devices that never
    touch that path.
    """

    def __init__(self, cfg: dict, refresher: WorklistRefresher) -> None:
        self._cfg = cfg
        self._refresher = refresher
        self._lock = threading.Lock()
        self._status: Dict[str, dict] = {}
        self._last_query_time: Optional[datetime] = None
        self._task: Optional[asyncio.Task] = None
        self._refresh_lock = asyncio.Lock()

    async def _poll_once(self) -> None:
        """One cycle: find candidates, batch-query the PACS, merge results."""
        now = datetime.now()
        since = self._last_query_time or (now - timedelta(hours=self._cfg['cold_start_lookback_hours']))

        entries, _, _ = await self._refresher._fetch_schedule(lab_id=None)

        candidates = []
        for entry in entries:
            request_id = entry.get('request_id')
            if not request_id:
                continue
            with self._lock:
                prior = self._status.get(request_id)
            if prior and prior.get('outcome') == 'performed':
                continue  # a study once found never un-happens
            modality = _MODALITY_CODE.get((entry.get('modality') or '').lower())
            if not modality:
                continue

            info = await self._refresher._enrich(request_id)
            cnp = info and info.get('cnp')
            if not cnp or not parse_cnp(cnp).get('valid'):
                logger.debug("Skipping request %s: no valid CNP", request_id)
                continue

            candidates.append({'request_id': request_id, 'cnp': cnp, 'modality': modality})
            if len(candidates) >= self._cfg['max_queries_per_cycle']:
                break

        if candidates:
            results = await asyncio.get_event_loop().run_in_executor(
                None, self._query_pacs_sync, candidates, since, now)
            with self._lock:
                self._status.update(results)

        self._last_query_time = now

    def _query_pacs_sync(self, candidates: List[dict], since: datetime, until: datetime) -> Dict[str, dict]:
        """Blocking: one association, one C-FIND per candidate, then release.
        Runs off the event loop via run_in_executor."""
        out: Dict[str, dict] = {}
        ae = AE(ae_title=self._cfg['calling_ae_title'])
        ae.add_requested_context(Verification)
        ae.add_requested_context(StudyRootQueryRetrieveInformationModelFind)
        ae.acse_timeout    = self._cfg['acse_timeout']
        ae.network_timeout = self._cfg['network_timeout']
        ae.dimse_timeout   = self._cfg['dimse_timeout']

        try:
            assoc = ae.associate(self._cfg['host'], self._cfg['port'],
                                  ae_title=self._cfg['called_ae_title'])
            if not assoc.is_established:
                logger.warning("PACS association failed (host=%s port=%d called_ae=%s)",
                                self._cfg['host'], self._cfg['port'], self._cfg['called_ae_title'])
                return out
            try:
                if not assoc.send_c_echo():
                    logger.warning("PACS C-ECHO failed — proceeding with C-FIND anyway")
                for c in candidates:
                    ident = self._build_identifier(c['cnp'], c['modality'], since, until)
                    # A query can return several matching studies (a PACS
                    # that ignores the ModalitiesInStudy matching key, or a
                    # patient with more than one study that day) — take the
                    # strongest classification across all of them rather
                    # than just the last response, so one wrong-modality
                    # match can't mask a real one found earlier.
                    outcome, detail = 'not_found', {}
                    try:
                        for status, ds in assoc.send_c_find(
                                ident, StudyRootQueryRetrieveInformationModelFind):
                            if status and status.Status in (0xFF00, 0xFF01) and ds is not None:
                                candidate_outcome, candidate_detail = self._classify(ds, c['modality'])
                                if _OUTCOME_RANK[candidate_outcome] > _OUTCOME_RANK[outcome]:
                                    outcome, detail = candidate_outcome, candidate_detail
                    except Exception as exc:
                        logger.warning("C-FIND failed for request %s: %s", c['request_id'], exc)
                        outcome = 'error'
                    out[c['request_id']] = {
                        'cnp': c['cnp'],
                        'modality': c['modality'],
                        'outcome': outcome,
                        **detail,
                        'checked_at': datetime.now().isoformat(timespec='seconds'),
                    }
            finally:
                assoc.release()
        except Exception as exc:
            logger.warning("PACS query batch failed: %s", exc)
        return out

    @staticmethod
    def _build_identifier(cnp: str, modality: str, since: datetime, until: datetime) -> 'Dataset':
        ds = Dataset()
        ds.QueryRetrieveLevel = 'STUDY'
        ds.PatientID = cnp
        ds.StudyDate = f"{since.strftime('%Y%m%d')}-{until.strftime('%Y%m%d')}"
        ds.ModalitiesInStudy = modality
        ds.NumberOfStudyRelatedInstances = ''
        ds.StudyInstanceUID = ''
        ds.StudyDescription = ''
        return ds

    @staticmethod
    def _classify(ds: 'Dataset', requested_modality: str) -> Tuple[str, dict]:
        """ModalitiesInStudy and NumberOfStudyRelatedInstances are both
        OPTIONAL return keys per the DICOM Study Root C-FIND model — some
        PACS omit or don't populate them. An absent instance count must not
        be read as "not performed".

        ModalitiesInStudy is also a matching key we send in the query, but
        that alone isn't trustworthy: some PACS silently ignore optional
        matching keys and return every study for the patient/date range
        regardless of modality. A study can also legitimately carry several
        modalities (e.g. ['CR', 'SR'] — an image series plus its structured
        report) where only one of them is the one we actually asked about.
        So cross-check the modality actually present in the response before
        ever calling something "performed" — otherwise a patient scheduled
        for an X-ray who instead had an ultrasound that same day would get
        the X-ray request wrongly marked as done.
        """
        modalities_raw = getattr(ds, 'ModalitiesInStudy', None)
        if modalities_raw not in (None, ''):
            found_modalities = [modalities_raw] if isinstance(modalities_raw, str) else list(modalities_raw)
            if requested_modality not in found_modalities:
                return 'not_found', {
                    'study_date': str(getattr(ds, 'StudyDate', '') or '') or None,
                    'instances': None,
                    'modalities_in_study': found_modalities,
                }

        n = getattr(ds, 'NumberOfStudyRelatedInstances', None)
        detail = {
            'study_date': str(getattr(ds, 'StudyDate', '') or '') or None,
            'instances':  int(n) if n not in (None, '') else None,
        }
        if n not in (None, ''):
            return ('performed' if int(n) > 0 else 'not_found'), detail
        return 'likely', detail  # study matched, instance count just wasn't returned

    async def _loop(self) -> None:
        while True:
            try:
                await self._poll_once()
            except Exception as exc:
                logger.warning("PACS poll cycle failed: %s", exc)
            await asyncio.sleep(self._cfg['poll_interval_seconds'])

    async def refresh_now(self) -> List[dict]:
        """Manual/frontend-triggered immediate check, throttled so rapid
        clicks can't hammer the PACS — a call already in flight just waits
        for it and returns its result instead of starting a second one."""
        async with self._refresh_lock:
            await self._poll_once()
        return self.status()

    def start(self) -> None:
        self._task = asyncio.get_event_loop().create_task(self._loop())

    def shutdown(self) -> None:
        if self._task is not None:
            self._task.cancel()

    def status(self) -> List[dict]:
        with self._lock:
            return [{'request_id': rid, **v} for rid, v in self._status.items()]


def start_pacs_checker(service_url: str, config) -> Optional[PacsChecker]:
    """Start the PACS checker if [pacs] host is configured. Returns the
    PacsChecker instance, or None if disabled (no host, pynetdicom missing,
    or no Hipocrate credentials).

    Must be called from inside a running asyncio event loop (e.g. inside
    hippobridge.init_app).
    """
    if not DICOM_AVAILABLE:
        logger.warning("pynetdicom/pydicom not installed — PACS study-check disabled. "
                       "Run: pip install pynetdicom pydicom")
        return None

    cfg = _load_config(config)
    if not cfg['host']:
        logger.info("[pacs] host not configured — PACS study-check disabled")
        return None
    if not cfg['username'] or not cfg['password']:
        logger.warning(
            "PACS checker Hipocrate credentials not configured (set username/password "
            "in [pacs] section of hippobridge.cfg, or export HYP_USER / HYP_PASS) "
            "— PACS study-check disabled"
        )
        return None

    refresher = WorklistRefresher(
        cache=WorklistCache(),
        service_url=service_url,
        username=cfg['username'],
        password=cfg['password'],
    )
    checker = PacsChecker(cfg, refresher)
    checker.start()
    logger.info(
        "PACS study-check started: host=%s:%d called_ae=%s calling_ae=%s poll=%ds cold_start_lookback=%dh",
        cfg['host'], cfg['port'], cfg['called_ae_title'], cfg['calling_ae_title'],
        cfg['poll_interval_seconds'], cfg['cold_start_lookback_hours'],
    )
    return checker
