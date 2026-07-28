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
import sys

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
          f"connecting with AE title '{needle}' anyway (expect it to be rejected).")
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


def _print_results(results: list) -> int:
    """Print one row per C-FIND match. Returns the number of matches."""
    header = (f"{'Patient':<28} {'PatientID':<15} {'Accession':<12} {'Mod':<4} "
              f"{'Scheduled':<15} {'Ward':<16} {'Referring physician':<24} Procedure")
    print(header)
    print('-' * len(header))

    count = 0
    for status, ds in results:
        if not status or status.Status != 0xFF00:
            continue
        count += 1
        sps = ds.ScheduledProcedureStepSequence[0]
        scheduled = f"{sps.ScheduledProcedureStepStartDate}{sps.ScheduledProcedureStepStartTime}".strip()
        print(f"{str(ds.PatientName):<28} {str(ds.PatientID):<15} "
              f"{str(ds.AccessionNumber):<12} {str(sps.Modality):<4} "
              f"{scheduled:<15} {str(getattr(ds, 'InstitutionalDepartmentName', '')):<16} "
              f"{str(ds.ReferringPhysicianName):<24} "
              f"{str(sps.ScheduledProcedureStepDescription)}")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='worklist.cfg', help="Path to worklist.cfg")
    parser.add_argument('--host', default='127.0.0.1', help="MWL server host")
    parser.add_argument('--profile', help="Device profile name or AE title (skips the interactive picker)")
    parser.add_argument('--date', default='', help="ScheduledProcedureStepStartDate filter: YYYYMMDD or YYYYMMDD-YYYYMMDD")
    parser.add_argument('--patient-name', default='', help="PatientName wildcard filter, e.g. POPESCU*")
    args = parser.parse_args()

    if not DICOM_AVAILABLE:
        print("pynetdicom/pydicom not installed. Run: pip install pynetdicom pydicom")
        return 1

    server_cfg, profiles = _load_config(args.config)
    if not profiles:
        print(f"No device profiles found in {args.config}")
        return 1

    profile = _find_profile(profiles, args.profile) if args.profile else _pick_profile(profiles)

    if len(profile['ae_title']) > 16:
        print(f"AE title '{profile['ae_title']}' exceeds the DICOM 16-character limit.")
        return 1

    print(f"\nConnecting as AE '{profile['ae_title']}' (profile: {profile['name']}) "
          f"to {args.host}:{server_cfg['port']} (called AE '{server_cfg['ae_title']}')...")

    ae = AE(ae_title=profile['ae_title'])
    ae.add_requested_context(Verification)
    ae.add_requested_context(ModalityWorklistInformationFind)

    assoc = ae.associate(args.host, server_cfg['port'], ae_title=server_cfg['ae_title'])
    if not assoc.is_established:
        print("Association failed — is the server running? Is the port/host correct?")
        return 1

    echo_status = assoc.send_c_echo()
    echo_ok = bool(echo_status) and echo_status.Status == 0x0000
    print(f"C-ECHO: {'OK' if echo_ok else f'FAILED (status={echo_status})'}")

    identifier = _build_identifier(args.patient_name, args.date)
    results = list(assoc.send_c_find(identifier, ModalityWorklistInformationFind))
    assoc.release()

    statuses = [s.Status for s, _ in results if s]
    if any(s == 0xA700 for s in statuses):
        print(f"\nC-FIND REJECTED (0xA700) — AE title '{profile['ae_title']}' is not authorised. "
              f"Add a [{profile['ae_title']}] section to {args.config} to authorise this device.")
        return 1

    print()
    count = _print_results(results)
    print(f"\n{count} entries returned")
    return 0


if __name__ == '__main__':
    sys.exit(main())
