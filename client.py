#!/usr/bin/env python3
"""
Client script to interact with the HippoBridge API.

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
import asyncio
import aiohttp
import argparse
import os
import sys
from urllib.parse import quote

# Overridden in main() from --base-url / HIPPOBRIDGE_URL; every request
# function reads this module global at call time, so setting it before any
# operation runs is enough — no need to thread it through every call.
BASE_URL = os.getenv("HIPPOBRIDGE_URL", "http://localhost:44660")

FHIR_PATIENT = "Patient"
FHIR_BUNDLE  = "Bundle"


def _seg(value: str) -> str:
    """URL-encode a path segment (e.g. an ID interpolated into /fhir/X/{id}).
    IDs are normally alnum, but this also covers a raw CNP/free-text value
    passed straight through by a caller who skipped resolution."""
    return quote(str(value), safe="")

# Simple LRU-style cache: evict oldest entry when full
_cnp_cache: dict = {}
_CNP_CACHE_MAX = 1000


def _cnp_cache_put(cnp: str, patient_code: str) -> None:
    if cnp in _cnp_cache:
        return
    if len(_cnp_cache) >= _CNP_CACHE_MAX:
        _cnp_cache.pop(next(iter(_cnp_cache)))  # evict oldest
    _cnp_cache[cnp] = patient_code


async def _get(session: aiohttp.ClientSession, path: str, params: dict = None) -> tuple[dict, bool]:
    """GET BASE_URL+path with optional query params; return (response_body, ok).
    params go through aiohttp's own encoding (session.get(..., params=...)) —
    never build the query string by hand, a raw f-string breaks on '&'/'#'/'%'
    in free-text values like a patient search term."""
    try:
        async with session.get(f"{BASE_URL}{path}", params=params) as resp:
            body = await resp.json()
            return body, resp.status == 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, False


async def _post(session: aiohttp.ClientSession, path: str, payload: dict) -> tuple[dict, bool]:
    """POST BASE_URL+path with JSON payload; return (response_body, ok)."""
    try:
        async with session.post(f"{BASE_URL}{path}", json=payload) as resp:
            body = await resp.json()
            return body, resp.status == 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, False


def _patient_display_name(patient: dict) -> str:
    names = patient.get("name", [])
    if not names:
        return "Unknown"
    name = names[0]
    if name.get("text"):
        return name["text"]
    given  = " ".join(name.get("given", []))
    family = name.get("family", "")
    return f"{given} {family}".strip() or "Unknown"


def _pick_patient_from_bundle(data: dict, context: str) -> str | None:
    """Return the id of the first patient in a Bundle, with a clear warning if multiple found."""
    entries = data.get("entry", [])
    if not entries:
        print(f"{context}: no patients in bundle")
        return None
    if len(entries) > 1:
        print(f"{context}: {len(entries)} patients found — using first match:")
        for i, e in enumerate(entries[:5], 1):
            p = e.get("resource", {})
            print(f"  {i}. {_patient_display_name(p)} (ID: {p.get('id', 'N/A')})")
        if len(entries) > 5:
            print(f"  … and {len(entries) - 5} more")
    patient = entries[0].get("resource", {})
    return patient.get("id")


async def search_patients(session: aiohttp.ClientSession, search_term: str) -> bool:
    """Search for patients and print results."""
    print(f"Searching for patients: '{search_term}'")
    data, ok = await _get(session, "/fhir/Patient", params={"q": search_term})
    if not ok:
        print(f"Patient search failed: {data.get('message', '')}")
        return False

    if data.get("resourceType") == FHIR_BUNDLE:
        entries = data.get("entry", [])
        print(f"Found {data.get('total', len(entries))} patient(s):")
        for i, entry in enumerate(entries, 1):
            p = entry.get("resource", {})
            print(f"  {i}. {_patient_display_name(p)} (ID: {p.get('id', 'N/A')})")
    elif data.get("resourceType") == FHIR_PATIENT:
        print(f"Found: {_patient_display_name(data)} (ID: {data.get('id', 'N/A')})")
    else:
        print("No patients found.")
    return True


async def get_patient(session: aiohttp.ClientSession, patient_id: str) -> bool:
    """Retrieve and display a patient by ID, CNP, or partial CNP."""
    resolved = await _resolve_patient_id(session, patient_id)
    if resolved:
        patient_id = resolved

    print(f"Retrieving patient: {patient_id}")
    data, ok = await _get(session, f"/fhir/Patient/{_seg(patient_id)}")
    if not ok:
        print(f"Patient retrieval failed: {data.get('message', '')}")
        return False

    print("\n--- Patient ---")
    print(f"ID: {data.get('id', 'N/A')}")
    print(f"Name: {_patient_display_name(data)}")
    if data.get("gender"):
        print(f"Gender: {data['gender']}")
    if data.get("birthDate"):
        print(f"Birth date: {data['birthDate']}")

    for ident in data.get("identifier", []):
        system = ident.get("system", "")
        value  = ident.get("value", "")
        if not value:
            continue
        label = "CNP" if "cnp" in system else "CID" if "cid" in system else system.split("/")[-1]
        print(f"{label}: {value}")

    checkout_ids = []
    checkin_ids  = []
    for ext in data.get("extension", []):
        url = ext.get("url", "")
        val = ext.get("valueString", "")
        if "checkout-ids" in url:
            checkout_ids = [v for v in val.split(",") if v.strip()]
        elif "checkin-ids" in url:
            checkin_ids = [v for v in val.split(",") if v.strip()]

    if checkout_ids:
        print(f"\nCheckout IDs ({len(checkout_ids)}):")
        for i, cid in enumerate(checkout_ids, 1):
            print(f"  {i}. {cid}")
    if checkin_ids:
        print(f"\nCheckin IDs ({len(checkin_ids)}):")
        for i, cid in enumerate(checkin_ids, 1):
            print(f"  {i}. {cid}")
    print("---------------")
    return True


async def get_report(session: aiohttp.ClientSession, report_id: str) -> bool:
    """Retrieve and display a DiagnosticReport by ID."""
    print(f"Retrieving report: {report_id}")
    data, ok = await _get(session, f"/fhir/DiagnosticReport/{_seg(report_id)}")
    if not ok:
        print(f"Report retrieval failed: {data.get('message', '')}")
        return False

    print("\n--- Diagnostic Report ---")
    print(f"ID: {data.get('id', 'N/A')}")
    if data.get("status"):
        print(f"Status: {data['status']}")
    if data.get("effectiveDateTime"):
        print(f"Date: {data['effectiveDateTime']}")

    code = data.get("code", {})
    code_text = code.get("text") or (code.get("coding") or [{}])[0].get("display", "")
    if code_text:
        print(f"Type: {code_text}")

    subject = data.get("subject", {})
    if subject.get("reference"):
        print(f"Patient: {subject['reference']}")

    for perf in data.get("performer", []):
        if perf.get("display"):
            print(f"Performer: {perf['display']}")

    if data.get("conclusion"):
        print(f"\nConclusion:\n{data['conclusion']}")

    for form in data.get("presentedForm", []):
        if form.get("data"):
            title = form.get("title", "")
            print(f"\n{'Result — ' + title if title else 'Result'}:\n{form['data']}")

    print("-------------------------")
    return True


async def get_imaging_study(session: aiohttp.ClientSession, study_id: str) -> bool:
    """Retrieve and display an ImagingStudy by ID."""
    print(f"Retrieving imaging study: {study_id}")
    data, ok = await _get(session, f"/fhir/ImagingStudy/{_seg(study_id)}")
    if not ok:
        print(f"Imaging study retrieval failed: {data.get('message', '')}")
        return False

    print("\n--- Imaging Study ---")
    print(f"ID: {data.get('id', 'N/A')}")
    if data.get("status"):
        print(f"Status: {data['status']}")
    if data.get("started"):
        print(f"Started: {data['started']}")
    if data.get("description"):
        print(f"Description: {data['description']}")

    # modality is an array in FHIR R4
    for mod in data.get("modality", []):
        label = mod.get("display") or mod.get("code", "")
        if label:
            print(f"Modality: {label}")

    subject = data.get("subject", {})
    if subject.get("reference"):
        print(f"Patient: {subject['reference']}")

    for perf in data.get("performer", []):
        actor = perf.get("actor", {})
        if actor.get("display"):
            print(f"Performer: {actor['display']}")

    referrer = data.get("referrer", {})
    if referrer.get("display"):
        print(f"Referrer: {referrer['display']}")

    for reason in data.get("reason", []):
        if reason.get("text"):
            print(f"Reason: {reason['text']}")

    for note in data.get("note", []):
        if note.get("text"):
            print(f"Note: {note['text']}")

    series_list = data.get("series", [])
    if series_list:
        print(f"\nSeries ({len(series_list)}):")
        for s in series_list:
            mod = s.get("modality", {})
            mod_label = mod.get("display") or mod.get("code", "")
            desc = s.get("description", "")
            parts = [f"#{s.get('number', '?')}"]
            if desc:
                parts.append(desc)
            if mod_label:
                parts.append(f"({mod_label})")
            print(f"  {' '.join(parts)}")

    print("---------------------")
    return True


async def get_checkout(session: aiohttp.ClientSession, checkout_id: str) -> bool:
    """Retrieve and display an Encounter (checkout) by ID."""
    print(f"Retrieving checkout: {checkout_id}")
    # Correct route: path parameter, not query string
    data, ok = await _get(session, f"/fhir/Encounter/{_seg(checkout_id)}")
    if not ok:
        print(f"Checkout retrieval failed: {data.get('message', '')}")
        return False

    print("\n--- Encounter ---")
    print(f"ID: {data.get('id', 'N/A')}")
    if data.get("status"):
        print(f"Status: {data['status']}")

    enc_class = data.get("class", {})
    if enc_class.get("display") or enc_class.get("code"):
        print(f"Class: {enc_class.get('display') or enc_class.get('code')}")

    for t in data.get("type", []):
        coding = (t.get("coding") or [{}])[0]
        if coding.get("display"):
            print(f"Type: {coding['display']}")

    subject = data.get("subject", {})
    if subject.get("reference"):
        print(f"Patient: {subject['reference']}")

    period = data.get("period", {})
    if period.get("start"):
        print(f"Admission: {period['start']}")
    if period.get("end"):
        print(f"Discharge: {period['end']}")

    for participant in data.get("participant", []):
        ind = participant.get("individual", {})
        if ind.get("display"):
            print(f"Participant: {ind['display']}")

    for reason in data.get("reasonCode", []):
        if reason.get("text"):
            print(f"Reason: {reason['text']}")

    for diag in data.get("diagnosis", []):
        cond = diag.get("condition", {})
        if cond.get("display"):
            print(f"Diagnosis: {cond['display']}")

    for note in data.get("note", []):
        if note.get("text"):
            print(f"Note: {note['text'][:200]}{'…' if len(note['text']) > 200 else ''}")

    print("-----------------")
    return True


async def get_analyses(session: aiohttp.ClientSession, patient_id: str,
                       analysis_type: str = None, datetime_filter: str = None) -> bool:
    """Retrieve and display ServiceRequests (analyses) for a patient."""
    resolved = await _resolve_patient_id(session, patient_id)
    if resolved:
        patient_id = resolved

    params = {"patient": patient_id}
    if analysis_type:
        params["type"] = analysis_type
    if datetime_filter:
        params["dt"] = datetime_filter

    print(f"Retrieving analyses for patient: {patient_id}")
    data, ok = await _get(session, "/fhir/ServiceRequest", params=params)
    if not ok:
        print(f"Analyses retrieval failed: {data.get('message', '')}")
        return False

    if data.get("resourceType") != FHIR_BUNDLE:
        print("No analyses found.")
        return True

    entries = data.get("entry", [])
    print(f"\nAnalyses ({len(entries)} found):")

    imaging_ids = []
    for i, entry in enumerate(entries, 1):
        sr = entry.get("resource", {})
        sr_id   = sr.get("id", "N/A")
        coding  = (sr.get("code", {}).get("coding") or [{}])[0]
        sr_type = coding.get("code", "unknown")
        sr_date = sr.get("authoredOn", "")
        print(f"  {i}. ID: {sr_id}  type: {sr_type}  date: {sr_date}")
        if sr_type in ("radio", "ct", "irm", "eco", "rads"):
            imaging_ids.append(sr_id)

    if imaging_ids:
        print(f"\nFetching reports for {len(imaging_ids)} imaging request(s):")
        for sr_id in imaging_ids:
            await get_report(session, sr_id)

    return True


async def get_task(session: aiohttp.ClientSession, task_id: str) -> bool:
    """Retrieve and display a request's workflow state (FHIR Task) by ID."""
    print(f"Retrieving task: {task_id}")
    data, ok = await _get(session, f"/fhir/Task/{_seg(task_id)}")
    if not ok:
        print(f"Task retrieval failed: {data.get('message', '')}")
        return False

    print("\n--- Task ---")
    print(f"ID: {data.get('id', 'N/A')}")
    if data.get("status"):
        print(f"Status: {data['status']}")
    period = data.get("executionPeriod", {})
    if period.get("start"):
        print(f"Started: {period['start']}")
    if period.get("end"):
        print(f"Ended: {period['end']}")
    focus = data.get("focus", {})
    if focus.get("reference"):
        print(f"ServiceRequest: {focus['reference']}")
    for note in data.get("note", []):
        if note.get("text"):
            print(f"Note: {note['text']}")
    print("------------")
    return True


async def get_specimen(session: aiohttp.ClientSession, specimen_id: str) -> bool:
    """Retrieve and display the lab/imaging handoff paperwork (FHIR Specimen) by ID."""
    print(f"Retrieving specimen: {specimen_id}")
    data, ok = await _get(session, f"/fhir/Specimen/{_seg(specimen_id)}")
    if not ok:
        print(f"Specimen retrieval failed: {data.get('message', '')}")
        return False

    print("\n--- Specimen ---")
    print(f"ID: {data.get('id', 'N/A')}")
    if data.get("status"):
        print(f"Status: {data['status']}")
    subject = data.get("subject", {})
    if subject.get("reference"):
        print(f"Patient: {subject['reference']}")
    if data.get("type", {}).get("text"):
        print(f"Laboratory: {data['type']['text']}")
    collection = data.get("collection", {})
    if collection.get("collectedDateTime"):
        print(f"Collected: {collection['collectedDateTime']}")
    for coll_note in data.get("note", []):
        if coll_note.get("text"):
            print(f"Note: {coll_note['text']}")
    print("----------------")
    return True


async def get_observations(session: aiohttp.ClientSession, patient_id: str,
                            start_date: str = None, end_date: str = None) -> bool:
    """Retrieve and display aggregated lab Observations for a patient."""
    resolved = await _resolve_patient_id(session, patient_id)
    if resolved:
        patient_id = resolved

    params = {"patient": patient_id}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date

    print(f"Retrieving observations for patient: {patient_id}")
    data, ok = await _get(session, "/fhir/Observation", params=params)
    if not ok:
        print(f"Observations retrieval failed: {data.get('message', '')}")
        return False

    if data.get("resourceType") != FHIR_BUNDLE:
        print("No observations found.")
        return True

    entries = data.get("entry", [])
    print(f"\nObservations ({len(entries)} found):")
    for entry in entries:
        obs = entry.get("resource", {})
        analyte = obs.get("code", {}).get("text", "?")
        date = obs.get("effectiveDateTime", "")
        vq = obs.get("valueQuantity")
        if vq is not None:
            value = f"{vq.get('value')}{' ' + vq['unit'] if vq.get('unit') else ''}"
        else:
            value = obs.get("valueString", "")
        flag = (obs.get("interpretation") or [{}])[0].get("text", "")
        ref = (obs.get("referenceRange") or [{}])[0].get("text", "")
        line = f"  {date}  {analyte}: {value}"
        if flag:
            line += f" ({flag})"
        if ref:
            line += f"  [ref: {ref}]"
        print(line)

    return True


async def get_whoami(session: aiohttp.ClientSession) -> bool:
    """Retrieve and display the logged-in Hipocrate user identity."""
    print("Retrieving current user identity")
    data, ok = await _get(session, "/api/whoami")
    if not ok:
        print(f"Whoami request failed: {data.get('message', '')}")
        return False

    print("\n--- Whoami ---")
    user = data.get("user", {})
    if user.get("display_name"):
        print(f"Name: {user['display_name']}")
    if user.get("username"):
        print(f"Username: {user['username']}")
    if user.get("id"):
        print(f"User ID: {user['id']}")
    if data.get("hipocrate_url"):
        print(f"Hipocrate URL: {data['hipocrate_url']}")
    if "can_write_reports" in data:
        print(f"Can write reports: {data['can_write_reports']}")
    print("--------------")
    return True


async def validate_cnp(session: aiohttp.ClientSession, cnp: str) -> bool:
    """Validate a Romanian CNP and print the result."""
    print(f"Validating CNP: {cnp}")
    data, ok = await _get(session, "/fhir/ValueSet/cnp", params={"id": cnp})
    if not ok:
        print(f"CNP validation request failed: {data.get('message', '')}")
        return False
    if data.get("valid"):
        print(f"Valid CNP — gender: {data.get('gender', '?')}, "
              f"born: {data.get('birth_date', '?')}, "
              f"county: {data.get('county_name', '?')}")
    else:
        print("Invalid CNP")
    return True


async def _resolve_patient_id(session: aiohttp.ClientSession, patient_id: str) -> str | None:
    """If patient_id looks like a CNP or partial CNP, resolve it to a patient code."""
    if patient_id.isdigit() and len(patient_id) == 13:
        if patient_id in _cnp_cache:
            return _cnp_cache[patient_id]
        val_data, val_ok = await _get(session, "/fhir/ValueSet/cnp", params={"id": patient_id})
        if not val_ok or not val_data.get("valid"):
            print(f"CNP {patient_id} invalid, using as-is")
            return None
        data, ok = await _get(session, "/fhir/Patient", params={"q": patient_id})
        if not ok:
            return None
        code = _extract_patient_code(data, f"CNP {patient_id}")
        if code:
            _cnp_cache_put(patient_id, code)
        return code

    if patient_id.endswith("*") and patient_id[:-1]:
        data, ok = await _get(session, "/fhir/Patient", params={"q": patient_id})
        if not ok:
            return None
        return _extract_patient_code(data, f"partial CNP {patient_id}")

    return None


def _extract_patient_code(data: dict, context: str) -> str | None:
    if data.get("resourceType") == FHIR_PATIENT:
        return data.get("id")
    if data.get("resourceType") == FHIR_BUNDLE:
        return _pick_patient_from_bundle(data, context)
    return None


async def main() -> int:
    global BASE_URL
    parser = argparse.ArgumentParser(description="HippoBridge API Client")
    parser.add_argument("--base-url", help=f"HippoBridge server URL (default: {BASE_URL}, or $HIPPOBRIDGE_URL)")
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-request timeout in seconds (default: 30)")
    parser.add_argument("--username", "-u", help="Username for authentication")
    parser.add_argument("--password", "-w", help="Password for authentication")
    parser.add_argument("--search",         "-s", help="Search term for patient search")
    parser.add_argument("--patient",        "-p", help="Patient ID / CNP to retrieve")
    parser.add_argument("--report",         "-r", help="DiagnosticReport ID to retrieve")
    parser.add_argument("--imaging-study",  "-i", help="ImagingStudy ID to retrieve")
    parser.add_argument("--checkout",       "-o", help="Encounter/checkout ID to retrieve")
    parser.add_argument("--analyses",       "-a", help="Patient ID to retrieve analyses for")
    parser.add_argument("--analysis-type",  "-t", help="Analysis type filter (radio, ct, irm, eco, rads, lab)")
    parser.add_argument("--datetime-filter","-d", help="Date/time filter ISO (YYYY-MM-DDTHH:MM:SS)")
    parser.add_argument("--cnp",            "-c", help="CNP to validate")
    parser.add_argument("--task",           "-k", help="Task (cerere) ID to retrieve workflow state for")
    parser.add_argument("--specimen",       "-x", help="Specimen ID to retrieve handoff paperwork for")
    parser.add_argument("--observations",   "-O", help="Patient ID to retrieve aggregated lab observations for")
    parser.add_argument("--start-date", help="Start date filter for --observations (YYYY-MM-DD)")
    parser.add_argument("--end-date",   help="End date filter for --observations (YYYY-MM-DD)")
    parser.add_argument("--whoami", action="store_true", help="Show the logged-in Hipocrate user identity")
    args = parser.parse_args()

    if args.base_url:
        BASE_URL = args.base_url.rstrip("/")

    username = args.username or os.getenv("HYP_USER")
    password = args.password or os.getenv("HYP_PASS")

    if not any([args.search, args.patient, args.report, args.imaging_study,
                args.checkout, args.analyses, args.cnp, args.task,
                args.specimen, args.observations, args.whoami]):
        print("Error: at least one operation flag is required")
        parser.print_help()
        return 1

    if not username or not password:
        print("Error: username and password required (--username/--password or HYP_USER/HYP_PASS)")
        return 1

    # HippoBridge uses HTTP Basic Auth on every request — no separate login endpoint
    auth = aiohttp.BasicAuth(username, password)
    timeout = aiohttp.ClientTimeout(total=args.timeout)
    async with aiohttp.ClientSession(auth=auth, timeout=timeout) as session:
        ops = [
            (args.search,        lambda: search_patients(session, args.search)),
            (args.patient,       lambda: get_patient(session, args.patient)),
            (args.report,        lambda: get_report(session, args.report)),
            (args.imaging_study, lambda: get_imaging_study(session, args.imaging_study)),
            (args.checkout,      lambda: get_checkout(session, args.checkout)),
            (args.analyses,      lambda: get_analyses(session, args.analyses,
                                                       args.analysis_type, args.datetime_filter)),
            (args.cnp,           lambda: validate_cnp(session, args.cnp)),
            (args.task,          lambda: get_task(session, args.task)),
            (args.specimen,      lambda: get_specimen(session, args.specimen)),
            (args.observations,  lambda: get_observations(session, args.observations,
                                                           args.start_date, args.end_date)),
            (args.whoami,        lambda: get_whoami(session)),
        ]
        for flag, coro_fn in ops:
            if flag:
                if not await coro_fn():
                    return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
