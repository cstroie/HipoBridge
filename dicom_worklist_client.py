#!/usr/bin/env python3
"""
Interactive DICOM Modality Worklist (MWL) SCU test client.

Picks a device profile from worklist.cfg, connects to the HippoBridge MWL
SCP as that device (C-ECHO then C-FIND), and prints the worklist it gets
back. Use this instead of dcmtk's findscu/echoscu for quick manual testing.

Copyright (C) 2025 Costin Stroie <costinstroie@eridu.eu.org>

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
import argparse
import json
import sys

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

try:
    from pydicom import Dataset
    from pydicom.sequence import Sequence
    from pynetdicom import AE
    from pynetdicom.sop_class import ModalityWorklistInformationFind, Verification
    DICOM_AVAILABLE = True
except ImportError:
    DICOM_AVAILABLE = False

from worklist import _load_config


def _pick_profile(profiles: list) -> dict:
    """Print a numbered list of device profiles and prompt for a choice."""
    print("\nDevice profiles (from worklist.cfg):\n")
    for i, p in enumerate(profiles, start=1):
        wards = ', '.join(p['wards']) if p['wards'] else 'any'
        window = f"{p['time_window_hours']:g}h" if p['time_window_hours'] else 'no limit'
        print(f"  {i}) {p['name']:<14} ae_title={p['ae_title']:<16} "
              f"modality={p['modality'] or 'any':<5} wards={wards:<20} window={window}")
    print()

    while True:
        choice = input(f"Select profile [1-{len(profiles)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(profiles):
            return profiles[int(choice) - 1]
        print("Invalid choice, try again.")


def _find_profile(profiles: list, name: str) -> dict:
    """Look up a profile by section name or ae_title (case-insensitive).

    Falls back to a synthetic, unregistered profile using `name` itself as the
    AE title — useful for deliberately testing the server's 0xA700 rejection
    of an unknown device.
    """
    needle = name.strip().upper()
    for p in profiles:
        if p['name'].upper() == needle or p['ae_title'].upper() == needle:
            return p
    print(f"No profile named or titled '{name}' found in worklist.cfg — "
          f"connecting with AE title '{needle}' anyway (expect it to be rejected).",
          file=sys.stderr)
    return {'name': name, 'ae_title': needle, 'modality': None, 'wards': [], 'time_window_hours': 0.0}


def _build_identifier(patient_name: str, date: str) -> 'Dataset':
    identifier = Dataset()
    identifier.QueryRetrieveLevel = 'WORKLIST'
    identifier.PatientName        = patient_name or ''
    identifier.PatientID          = ''
    identifier.AccessionNumber    = ''
    sps = Dataset()
    sps.ScheduledProcedureStepStartDate = date or ''
    sps.Modality                        = ''
    identifier.ScheduledProcedureStepSequence = Sequence([sps])
    return identifier


def _build_records(results: list) -> list:
    """Turn matched (status, Dataset) pairs into plain dicts for table/json/yaml output."""
    records = []
    for status, ds in results:
        if not status or status.Status != 0xFF00:
            continue
        sps = ds.ScheduledProcedureStepSequence[0]
        records.append({
            'patient_name':          str(ds.PatientName),
            'patient_id':            str(ds.PatientID),
            'accession_number':      str(ds.AccessionNumber),
            'modality':              str(sps.Modality),
            'scheduled_date':        str(sps.ScheduledProcedureStepStartDate),
            'scheduled_time':        str(sps.ScheduledProcedureStepStartTime),
            'ward':                  str(getattr(ds, 'InstitutionalDepartmentName', '')),
            'referring_physician':   str(ds.ReferringPhysicianName),
            'procedure_description': str(sps.ScheduledProcedureStepDescription),
            'procedure_id':          str(sps.ScheduledProcedureStepID),
            'priority':              str(getattr(ds, 'RequestedProcedurePriority', '')),
        })
    return records


def _render_table(records: list) -> None:
    header = (f"{'Patient':<28} {'PatientID':<15} {'Accession':<12} {'Mod':<4} "
              f"{'Scheduled':<15} {'Ward':<16} {'Referring physician':<24} Procedure")
    print(header)
    print('-' * len(header))
    for r in records:
        scheduled = f"{r['scheduled_date']}{r['scheduled_time']}".strip()
        print(f"{r['patient_name']:<28} {r['patient_id']:<15} "
              f"{r['accession_number']:<12} {r['modality']:<4} "
              f"{scheduled:<15} {r['ward']:<16} "
              f"{r['referring_physician']:<24} "
              f"{r['procedure_description']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='worklist.cfg', help="Path to worklist.cfg")
    parser.add_argument('--host', default='127.0.0.1', help="MWL server host")
    parser.add_argument('--profile', help="Device profile name or AE title (skips the interactive picker)")
    parser.add_argument('--date', default='', help="ScheduledProcedureStepStartDate filter: YYYYMMDD or YYYYMMDD-YYYYMMDD")
    parser.add_argument('--patient-name', default='', help="PatientName wildcard filter, e.g. POPESCU*")
    parser.add_argument('--format', choices=['table', 'json', 'yaml'], default='table',
                        help="Output format. json/yaml print only the result records to stdout "
                             "(status messages go to stderr) — for scripting.")
    args = parser.parse_args()

    scripted = args.format != 'table'
    # Status/progress messages: stdout for the human table view, stderr when
    # scripted so stdout stays pure data (pipeable into jq etc).
    status = (lambda msg: print(msg, file=sys.stderr)) if scripted else print

    if args.format == 'yaml' and not YAML_AVAILABLE:
        print("PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
        return 1

    if not DICOM_AVAILABLE:
        status("pynetdicom/pydicom not installed. Run: pip install pynetdicom pydicom")
        return 1

    server_cfg, profiles = _load_config(args.config)
    if not profiles:
        status(f"No device profiles found in {args.config}")
        return 1

    profile = _find_profile(profiles, args.profile) if args.profile else _pick_profile(profiles)

    if len(profile['ae_title']) > 16:
        status(f"AE title '{profile['ae_title']}' exceeds the DICOM 16-character limit.")
        return 1

    status(f"\nConnecting as AE '{profile['ae_title']}' (profile: {profile['name']}) "
           f"to {args.host}:{server_cfg['port']} (called AE '{server_cfg['ae_title']}')...")

    ae = AE(ae_title=profile['ae_title'])
    ae.add_requested_context(Verification)
    ae.add_requested_context(ModalityWorklistInformationFind)

    assoc = ae.associate(args.host, server_cfg['port'], ae_title=server_cfg['ae_title'])
    if not assoc.is_established:
        status("Association failed — is the server running? Is the port/host correct?")
        return 1

    echo_status = assoc.send_c_echo()
    echo_ok = bool(echo_status) and echo_status.Status == 0x0000
    status(f"C-ECHO: {'OK' if echo_ok else f'FAILED (status={echo_status})'}")

    identifier = _build_identifier(args.patient_name, args.date)
    results = list(assoc.send_c_find(identifier, ModalityWorklistInformationFind))
    assoc.release()

    statuses = [s.Status for s, _ in results if s]
    if any(s == 0xA700 for s in statuses):
        status(f"\nC-FIND REJECTED (0xA700) — AE title '{profile['ae_title']}' is not authorised. "
               f"Add a [{profile['ae_title']}] section to {args.config} to authorise this device.")
        return 1

    records = _build_records(results)
    if args.format == 'json':
        print(json.dumps(records, indent=2))
    elif args.format == 'yaml':
        print(yaml.safe_dump(records, sort_keys=False, allow_unicode=True))
    else:
        print()
        _render_table(records)

    status(f"\n{len(records)} entries returned")
    return 0


if __name__ == '__main__':
    sys.exit(main())
