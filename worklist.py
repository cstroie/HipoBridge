#!/usr/bin/env python3
"""DICOM Modality Worklist (MWL) SCP server.

Serves Scheduled Procedure Steps from the Hipocrate schedule to imaging
devices via the DICOM C-FIND protocol (MWL SOP Class 1.2.840.10008.5.1.4.31).

Architecture:
- An asyncio background task (WorklistRefresher) polls HipoClientSchedule
  and enriches each entry with patient demographics.
- The refresher builds a list of pydicom Datasets and stores them in a
  thread-safe WorklistCache.
- A pynetdicom AE (WorklistServer) runs in a daemon thread, reads from the
  cache, and responds to C-FIND requests.

Configuration: worklist.cfg (alongside hipobridge.cfg).

Copyright (C) 2025 Costin Stroie <costinstroie@eridu.eu.org>
"""

import asyncio
import configparser
import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

try:
    from pydicom import Dataset
    from pydicom.sequence import Sequence
    from pydicom.uid import generate_uid
    from pynetdicom import AE, evt
    from pynetdicom.sop_class import ModalityWorklistInformationFind
    DICOM_AVAILABLE = True
except ImportError:
    DICOM_AVAILABLE = False

from hipoclient import HipoClientSchedule, HipoClientCerere, HipoClientPatient

logger = logging.getLogger('Worklist')

# Maps schedule modality slugs → DICOM modality codes.
# 'irm' is the slug HipoClientSchedule uses for MRI (from _lab_to_modality).
_MODALITY_CODE: Dict[str, str] = {
    'radio':  'CR',
    'eco':    'US',
    'ct':     'CT',
    'irm':    'MR',
    'mri':    'MR',
    'fluoro': 'RF',
    'rads':   'RF',
    'lab':    'LAB',
}

# HipoClientSchedule._FHIR_STATUS values that mean the study is still pending.
# Entries with any other status (completed, ended, entered-in-error) are excluded.
_ACTIVE_FHIR_STATUSES = frozenset({'on-hold', 'draft', 'active'})

# Hipocrate status text → FHIR status (mirrors HipoClientSchedule._FHIR_STATUS).
_HIPOCRATE_TO_FHIR: Dict[str, str] = {
    'cerere netrimisa':                   'on-hold',
    'trimisa in laborator':               'draft',
    'primita in laborator':               'draft',
    'in lucru(nv)':                       'active',
    'fara analize':                       'entered-in-error',
    'cerere completata':                  'completed',
    'cerere completata/partial validata': 'completed',
    'terminata':                          'ended',
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _load_config(config_path: str) -> Tuple[dict, List[dict]]:
    """Parse worklist.cfg.

    Returns (server_cfg, device_profiles).

    server_cfg keys: ae_title, port, refresh_minutes, username, password.
    device_profiles: list of dicts with keys name, ae_title, modality,
                     sections (list), time_window_hours.
    """
    config = configparser.ConfigParser()
    config.read(config_path)

    server = {
        'ae_title':        config.get('worklist', 'ae_title', fallback='HIPPOBRIDGE'),
        'port':            config.getint('worklist', 'port', fallback=11112),
        'refresh_minutes': config.getfloat('worklist', 'refresh_minutes', fallback=5.0),
        'username':        config.get('worklist', 'username',
                                      fallback=os.getenv('HYP_USER', '')),
        'password':        config.get('worklist', 'password',
                                      fallback=os.getenv('HYP_PASS', '')),
    }

    profiles = []
    for section in config.sections():
        if section.lower() == 'worklist':
            continue
        ae = config.get(section, 'ae_title', fallback='').strip()
        if not ae:
            continue
        modality = config.get(section, 'modality', fallback='').strip().lower() or None
        sections_raw = config.get(section, 'sections', fallback='').strip()
        sections = [s.strip() for s in sections_raw.split(',') if s.strip()]
        time_window = config.getfloat(section, 'time_window_hours', fallback=0.0)
        profiles.append({
            'name':              section,
            'ae_title':          ae.upper(),
            'modality':          modality,
            'sections':          sections,
            'time_window_hours': time_window,
        })

    return server, profiles


# ---------------------------------------------------------------------------
# DICOM Dataset helpers
# ---------------------------------------------------------------------------

# Academic / medical title stems that belong in the DICOM PN Prefix component (4th).
# Each entry is the normalised form WITHOUT a trailing dot, uppercased.
# Matching accepts the stem with or without a trailing dot (standalone),
# and the stem followed by '.' then letters (glued to the family name).
# Internal dots (S.L, A.S) are preserved as-is so S.L. round-trips correctly.
_PREFIX_STEMS: frozenset = frozenset({
    'DR',                           # Doctor
    'PROF',                         # Profesor
    'CONF',                         # Conferentiar
    'SL', 'S.L',                    # Sef Lucrari
    'AS', 'A.S', 'ASIST',           # Asistent
    'UNIV',                         # Universitar (used in PROF. UNIV. DR.)
    'ACAD',                         # Academician
    'ING',                          # Inginer
    'EC',                           # Economist
})

# Sorted longest-first so that greedy matching tries 'S.L' before 'S', etc.
_PREFIX_STEMS_SORTED: list = sorted(_PREFIX_STEMS, key=len, reverse=True)


def _is_standalone_prefix(tok: str) -> bool:
    """True if tok is a known title token (with or without trailing dot)."""
    return tok.upper().rstrip('.') in _PREFIX_STEMS


def _split_glued_prefix(tok: str) -> tuple:
    """If tok begins with 'STEM.' followed by at least one letter, return
    (prefix_with_dot, remainder); otherwise return (None, None).

    Works with internal-dot stems: 'S.L.POPESCU' → ('S.L.', 'POPESCU').
    Tries longest stems first to avoid partial matches.
    """
    upper = tok.upper()
    for stem in _PREFIX_STEMS_SORTED:
        candidate = stem + '.'
        if upper.startswith(candidate) and len(tok) > len(candidate) and tok[len(candidate)].isalpha():
            return tok[:len(candidate)], tok[len(candidate):]
    return None, None


def _name_to_dicom(name: str) -> str:
    """Convert a name string to DICOM PN 'Family^Given^Middle^Prefix'.

    Handles:
    - Standalone titles:      'DR. OSSEBI GUY BLANCHARD'   → 'OSSEBI^GUY^BLANCHARD^DR.'
    - Multiple titles:        'CONF. UNIV. DR. STAN MIHAI'  → 'STAN^MIHAI^^CONF. UNIV. DR.'
    - Glued to family name:   'DR.STEFAN ELENA ELIS'        → 'STEFAN^ELENA^ELIS^DR.'
    - Internal-dot title:     'S.L. POPA ION'               → 'POPA^ION^^S.L.'
    - No title:               'IONESCU MARIA'               → 'IONESCU^MARIA'
    """
    if not name:
        return ''
    parts = name.strip().split()
    if not parts:
        return ''

    # Peel off consecutive standalone prefix tokens.
    prefix_tokens = []
    while parts and _is_standalone_prefix(parts[0]):
        prefix_tokens.append(parts[0])
        parts = parts[1:]

    # No standalone prefix? Check for a prefix glued to the first token.
    if not prefix_tokens and parts:
        glued_prefix, remainder = _split_glued_prefix(parts[0])
        if glued_prefix:
            prefix_tokens.append(glued_prefix)
            parts[0] = remainder

    prefix = ' '.join(prefix_tokens)

    if not parts:
        return prefix

    if prefix:
        family = parts[0]
        given  = parts[1] if len(parts) > 1 else ''
        middle = '^'.join(parts[2:]) if len(parts) > 2 else ''
        return f'{family}^{given}^{middle}^{prefix}'

    return '^'.join(parts)


def _date_to_dicom(date_str: str) -> str:
    """Convert 'YYYY-MM-DD' to DICOM DA 'YYYYMMDD'."""
    return date_str.replace('-', '')[:8] if date_str else ''


def _time_to_dicom(dt_str: str) -> str:
    """Extract HH:MM from 'YYYY-MM-DD HH:MM' and return DICOM TM 'HHMM00'."""
    if not dt_str or ' ' not in dt_str:
        return ''
    return dt_str.split(' ', 1)[1].replace(':', '') + '00'


def _sex_to_dicom(sex: str) -> str:
    """Convert 'male'/'female' to DICOM CS 'M'/'F'/'O'."""
    s = (sex or '').lower()
    return {'male': 'M', 'female': 'F'}.get(s, 'O')


def _build_dataset(entry: dict, patient_info: Optional[dict]) -> Dataset:
    """Build a pydicom Dataset for one MWL Scheduled Procedure Step."""
    ds = Dataset()

    # Patient demographics (enriched when available, falls back to schedule data)
    if patient_info:
        patient_name = _name_to_dicom(patient_info.get('name') or entry.get('patient_name', ''))
        patient_id   = patient_info.get('id', '')
        birth_date   = _date_to_dicom(patient_info.get('birth_date', ''))
        sex          = _sex_to_dicom(patient_info.get('sex', ''))
    else:
        patient_name = _name_to_dicom(entry.get('patient_name', ''))
        patient_id   = entry.get('request_id', '')
        birth_date   = ''
        sex          = 'O'

    ds.PatientName      = patient_name
    ds.PatientID        = patient_id
    ds.PatientBirthDate = birth_date
    ds.PatientSex       = sex

    # Order-level attributes
    request_id   = entry.get('request_id', '')
    request_code = entry.get('request_code', '')
    lab_display  = entry.get('laboratory', '')

    ds.AccessionNumber               = request_code
    ds.ReferringPhysicianName        = _name_to_dicom(entry.get('requested_by', ''))
    ds.RequestedProcedureDescription = lab_display
    ds.RequestedProcedureID          = request_id
    ds.StudyInstanceUID              = (
        f'1.2.840.99999999.1.{request_id}' if request_id else generate_uid()
    )

    # Scheduled Procedure Step Sequence (mandatory for MWL)
    sps = Dataset()
    dt_str = entry.get('date_time', '')
    sps.ScheduledProcedureStepStartDate = _date_to_dicom(dt_str.split(' ')[0] if dt_str else '')
    sps.ScheduledProcedureStepStartTime = _time_to_dicom(dt_str)
    sps.Modality                         = _MODALITY_CODE.get(entry.get('modality') or '', 'OT')
    sps.ScheduledProcedureStepDescription = lab_display
    sps.ScheduledProcedureStepID          = request_id
    sps.ScheduledStationAETitle            = ''
    sps.ScheduledPerformingPhysicianName   = _name_to_dicom(entry.get('requested_by', ''))

    ds.ScheduledProcedureStepSequence = Sequence([sps])

    return ds


# ---------------------------------------------------------------------------
# Thread-safe cache
# ---------------------------------------------------------------------------

class WorklistCache:
    """Thread-safe store of pre-built DICOM Datasets and their raw schedule dicts."""

    def __init__(self) -> None:
        self._lock    = threading.Lock()
        self._entries: List[Dataset] = []
        self._raw:     List[dict]    = []
        self._updated_at: Optional[datetime] = None

    def update(self, entries: List[Dataset], raw: List[dict]) -> None:
        with self._lock:
            self._entries    = entries
            self._raw        = raw
            self._updated_at = datetime.now()

    def snapshot(self) -> Tuple[List[Dataset], List[dict]]:
        """Return copies of the current cache contents (safe for the calling thread)."""
        with self._lock:
            return list(self._entries), list(self._raw)

    @property
    def updated_at(self) -> Optional[datetime]:
        with self._lock:
            return self._updated_at


# ---------------------------------------------------------------------------
# DICOM SCP
# ---------------------------------------------------------------------------

class WorklistServer:
    """pynetdicom AE configured as a C-FIND SCP for the MWL SOP Class."""

    def __init__(self, cache: WorklistCache, profiles: List[dict],
                 server_cfg: dict) -> None:
        self._cache     = cache
        self._profiles  = {p['ae_title']: p for p in profiles}
        self._ae_title  = server_cfg['ae_title']
        self._port      = server_cfg['port']
        self._unknown_log = logging.getLogger('Worklist.UnknownAE')

    def _profile_for(self, calling_ae: str) -> Optional[dict]:
        return self._profiles.get(calling_ae.strip().upper())

    @staticmethod
    def _date_in_range(entry_date: str, query_range: str) -> bool:
        """True if entry_date (YYYYMMDD) falls within the DICOM date range string."""
        if not query_range or not entry_date:
            return True
        if '-' in query_range:
            lo, hi = query_range.split('-', 1)
            if lo and entry_date < lo:
                return False
            if hi and entry_date > hi:
                return False
        else:
            if entry_date != query_range:
                return False
        return True

    @staticmethod
    def _matches_cfind(ds: Dataset, identifier: Dataset) -> bool:
        """Apply C-FIND matching keys from the SCU's request identifier."""
        # Patient name: wildcard match (strip *, ? → substring)
        req_pn = str(getattr(identifier, 'PatientName', '') or '')
        if req_pn and req_pn not in ('*', ''):
            pattern = req_pn.replace('*', '').replace('?', '').upper()
            if pattern and pattern not in str(ds.PatientName).upper():
                return False

        # Accession number: exact match
        req_acc = str(getattr(identifier, 'AccessionNumber', '') or '')
        if req_acc and req_acc not in ('*', ''):
            if str(ds.AccessionNumber) != req_acc:
                return False

        # ScheduledProcedureStepSequence matching keys
        sps_seq = getattr(identifier, 'ScheduledProcedureStepSequence', None)
        if sps_seq and len(sps_seq) > 0:
            req_sps  = sps_seq[0]
            ds_sps   = ds.ScheduledProcedureStepSequence[0]

            # Date (or date range)
            req_date = str(getattr(req_sps, 'ScheduledProcedureStepStartDate', '') or '')
            if req_date:
                entry_date = str(getattr(ds_sps, 'ScheduledProcedureStepStartDate', '') or '')
                if not WorklistServer._date_in_range(entry_date, req_date):
                    return False

            # Modality
            req_mod = str(getattr(req_sps, 'Modality', '') or '')
            if req_mod and req_mod not in ('*', ''):
                if str(ds_sps.Modality) != req_mod:
                    return False

        return True

    def _filter(self, entries: List[Dataset], raw: List[dict],
                profile: Optional[dict], calling_ae: str) -> List[Dataset]:
        """Apply device profile filters and return matching Datasets."""
        now = datetime.now()
        result = []

        for ds, r in zip(entries, raw):
            # Status: exclude completed / ended / error entries
            if r.get('_fhir_status') not in _ACTIVE_FHIR_STATUSES:
                continue

            if profile:
                # Modality filter
                target_mod = profile.get('modality')
                if target_mod and r.get('modality') != target_mod:
                    continue

                # Section filter (exact match; empty list = all sections)
                target_sections = profile.get('sections') or []
                if target_sections and r.get('section', '') not in target_sections:
                    continue

                # Time window: exclude entries too far in the future
                time_window = profile.get('time_window_hours', 0.0)
                if time_window > 0:
                    dt_str = r.get('date_time', '')
                    if dt_str:
                        try:
                            entry_dt = datetime.strptime(dt_str[:16], '%Y-%m-%d %H:%M')
                            if entry_dt > now + timedelta(hours=time_window):
                                continue
                        except ValueError:
                            pass

            # Stamp the ScheduledStationAETitle with the calling device's AE title.
            # We modify a copy of the SPS so the cached Dataset is not mutated.
            sps_orig = ds.ScheduledProcedureStepSequence[0]
            sps_copy = Dataset()
            sps_copy.update(sps_orig)
            sps_copy.ScheduledStationAETitle = calling_ae
            ds_out = Dataset()
            ds_out.update(ds)
            ds_out.ScheduledProcedureStepSequence = Sequence([sps_copy])

            result.append(ds_out)

        return result

    def handle_find(self, event):
        """C-FIND SCP handler (called by pynetdicom in its own thread)."""
        calling_ae = (event.assoc.requestor.ae_title or '').strip()
        identifier = event.identifier

        profile = self._profile_for(calling_ae)
        if profile is None:
            self._unknown_log.warning(
                "Unknown AE title '%s' — serving unfiltered worklist. "
                "Add a [%s] section to worklist.cfg to configure this device.",
                calling_ae, calling_ae,
            )

        entries, raw = self._cache.snapshot()
        candidates = self._filter(entries, raw, profile, calling_ae)

        count = 0
        for ds in candidates:
            if self._matches_cfind(ds, identifier):
                yield 0xFF00, ds   # C-FIND Pending
                count += 1

        logger.info(
            "C-FIND from '%s': %d/%d entries%s",
            calling_ae, count, len(entries),
            f" (profile: {profile['name']})" if profile else " (unfiltered)",
        )

    def serve(self) -> None:
        """Start the DICOM SCP. Blocks until the process exits."""
        if not DICOM_AVAILABLE:
            logger.error("pynetdicom/pydicom not installed — DICOM MWL disabled")
            return

        ae = AE(ae_title=self._ae_title)
        ae.add_supported_context(ModalityWorklistInformationFind)

        logger.info(
            "DICOM MWL SCP listening on port %d (AE: %s)", self._port, self._ae_title
        )
        ae.start_server(('', self._port), block=True,
                        evt_handlers=[(evt.EVT_C_FIND, self.handle_find)])


# ---------------------------------------------------------------------------
# Async refresher
# ---------------------------------------------------------------------------

class WorklistRefresher:
    """Asyncio background task: fetches schedule and enriches patient data."""

    def __init__(self, cache: WorklistCache, service_url: str,
                 username: str, password: str, refresh_interval: float) -> None:
        self._cache    = cache
        self._svc_url  = service_url
        self._username = username
        self._password = password
        self._interval = refresh_interval   # minutes
        # Per-request_id patient info cache (cleared when entry leaves the schedule)
        self._patient_cache: Dict[str, dict] = {}

    def _client(self, cls):
        """Return a HipoClient subclass instance authenticated with the service account."""
        c = cls(self._svc_url)
        c.set_credentials(self._username, self._password)
        return c

    async def _enrich(self, request_id: str) -> Optional[dict]:
        """Fetch patient demographics for one request_id. Returns cached result if known."""
        if request_id in self._patient_cache:
            return self._patient_cache[request_id]

        try:
            cerere = self._client(HipoClientCerere)
            cerere_data = await cerere.fetch_and_parse(id=request_id)
            patient_id = cerere_data.get('patient.id')
            if not patient_id:
                return None

            patient_client = self._client(HipoClientPatient)
            patient_data = await patient_client.fetch_and_parse(id=patient_id)
            if patient_data.get('status') == 'error':
                return None

            info = {
                'id':         patient_id,
                'name':       patient_data.get('patient.name'),
                'birth_date': patient_data.get('patient.birth_date'),
                'sex':        patient_data.get('patient.sex'),
            }
            self._patient_cache[request_id] = info
            return info

        except Exception as exc:
            logger.warning("Patient enrichment failed for request %s: %s", request_id, exc)
            return None

    async def _fetch_schedule(self) -> List[dict]:
        """Pull the schedule from Hipocrate.

        Fetches yesterday through 4 days ahead so that even MRI devices with
        a 72-hour window always see their full horizon.
        """
        start = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        end   = (datetime.now() + timedelta(days=4)).strftime('%Y-%m-%d')

        client = self._client(HipoClientSchedule)
        data = await client.fetch_and_parse(start_date=start, end_date=end, force=True)

        if data.get('status') == 'error':
            logger.error("Schedule fetch failed: %s", data.get('message'))
            return []

        entries = data.get('requests') or []
        for r in entries:
            status_key = (r.get('status') or '').lower()
            r['_fhir_status'] = _HIPOCRATE_TO_FHIR.get(status_key, 'unknown')

        return entries

    async def refresh(self) -> None:
        """One refresh cycle: fetch → enrich → build Datasets → update cache."""
        logger.debug("Worklist refresh starting")
        entries = await self._fetch_schedule()
        if not entries:
            logger.warning("Empty schedule — keeping previous worklist cache")
            return

        # Evict patient cache for requests that left the schedule
        current_ids = {e['request_id'] for e in entries if e.get('request_id')}
        for stale in [k for k in self._patient_cache if k not in current_ids]:
            del self._patient_cache[stale]

        # Only enrich active entries (no point enriching completed ones)
        active = [e for e in entries if e.get('_fhir_status') in _ACTIVE_FHIR_STATUSES]

        # Bounded concurrency: 2 patients at a time = max 4 Hipocrate calls,
        # leaving capacity for normal web traffic through the global semaphore.
        sem = asyncio.Semaphore(2)

        async def _bounded(entry):
            async with sem:
                return await self._enrich(entry.get('request_id', ''))

        infos = await asyncio.gather(*[_bounded(e) for e in active], return_exceptions=True)
        patient_map = {}
        for entry, info in zip(active, infos):
            if isinstance(info, dict):
                patient_map[entry.get('request_id')] = info

        if not DICOM_AVAILABLE:
            logger.warning("pynetdicom not available — skipping Dataset build")
            return

        datasets: List[Dataset] = []
        raw_out:  List[dict]    = []
        for entry in entries:
            rid = entry.get('request_id')
            try:
                ds = _build_dataset(entry, patient_map.get(rid))
                datasets.append(ds)
                raw_out.append(entry)
            except Exception as exc:
                logger.warning("Dataset build failed for request %s: %s", rid, exc)

        self._cache.update(datasets, raw_out)
        logger.info(
            "Worklist refreshed: %d entries total, %d active",
            len(datasets), len(active),
        )

    async def run(self) -> None:
        """Loop: refresh immediately on startup, then every refresh_interval minutes."""
        while True:
            try:
                await self.refresh()
            except Exception as exc:
                logger.error("Worklist refresh error: %s", exc)
            await asyncio.sleep(self._interval * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def start_worklist(service_url: str,
                   config_path: str = 'worklist.cfg') -> Optional['asyncio.Task']:
    """Start the DICOM MWL server if worklist.cfg exists and is properly configured.

    Returns the asyncio Task for the WorklistRefresher, or None if the server
    was not started (config missing, credentials absent, or pynetdicom not installed).

    Must be called from inside a running asyncio event loop (e.g. inside init_app).
    """
    config_path = os.path.join(os.path.dirname(__file__), config_path) \
        if not os.path.isabs(config_path) else config_path

    if not os.path.exists(config_path):
        logger.info("worklist.cfg not found — DICOM MWL server disabled")
        return None

    if not DICOM_AVAILABLE:
        logger.warning("pynetdicom/pydicom not installed — DICOM MWL server disabled. "
                       "Run: pip install pynetdicom pydicom")
        return None

    server_cfg, profiles = _load_config(config_path)

    if not server_cfg.get('username') or not server_cfg.get('password'):
        logger.warning(
            "Worklist credentials not configured (set username/password in "
            "[worklist] section of worklist.cfg, or export HYP_USER / HYP_PASS) "
            "— DICOM MWL server disabled"
        )
        return None

    cache = WorklistCache()

    refresher = WorklistRefresher(
        cache=cache,
        service_url=service_url,
        username=server_cfg['username'],
        password=server_cfg['password'],
        refresh_interval=server_cfg['refresh_minutes'],
    )

    server = WorklistServer(cache=cache, profiles=profiles, server_cfg=server_cfg)

    # pynetdicom's start_server() is blocking — run it in a daemon thread.
    t = threading.Thread(target=server.serve, daemon=True, name='DicomMWL')
    t.start()

    # Schedule the async refresher in the current event loop.
    task = asyncio.create_task(refresher.run(), name='WorklistRefresher')

    logger.info(
        "DICOM MWL server started: AE=%s port=%d refresh=%.1fmin profiles=%d",
        server_cfg['ae_title'], server_cfg['port'],
        server_cfg['refresh_minutes'], len(profiles),
    )
    return task
