#!/usr/bin/env python3
"""
HipoBridge - FHIR Bridge for Hipocrate Medical System

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

FHIR R4 API bridge to Hipocrate: scrapes HTML on every request, no database.
Routes: /api/* returns raw HipoData JSON; /fhir/* returns FHIR R4 resources.
Config: hipobridge.cfg (defaults) overridden by local.cfg (not tracked by git).
"""
import asyncio
import os
from aiohttp import web
from typing import Dict, Any
import json
import logging
import functools
from datetime import datetime, timezone
import configparser
import base64

from fhir import OperationOutcome, Resource

from hipoclient import ANALYSIS_TYPES
from hipoclient import HipoClient, HipoClientPatient, HipoClientPatientSearch, HipoClientImagingStudy, HipoClientDiagnosticReport, HipoClientServiceRequest, HipoClientServiceRequestSearch, HipoClientCheckout, HipoClientCheckin, HipoClientCheckup, HipoClientSchedule, HipoClientCerere, HipoClientPresentation, HipoClientObservationBundle, HipoClientWhoami, HipoClientReportWrite, HipoClientReportValidate, HipoClientCererePerform
from hipoclient import user_session_manager, url_cache
from urlcache import FilesystemCache
from hipodata import HipoData

from extractors import parse_cnp
from markdown import markdown_to_html
from worklist import start_worklist

logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper(), logging.INFO),
    format='%(asctime)s | %(levelname)8s | %(message)s'
)
logger = logging.getLogger('HipoBridge')

DEFAULT_CONFIG = {
    'server': {
        'port': '44660',
        'host': '0.0.0.0'
    },
    'hipocrate': {
        'service_url': 'http://127.0.0.1/hipocrate'
    },
    'cache': {
        'dir': '',
        'ttl': '604800',
        'max_age_days': '30',
    },
    'radiology': {
        'allowed_radiologists': '',
    },
}


def get_basic_auth(request):
    """Extract (username, password) from Basic Auth header, or None."""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Basic '):
        return None

    try:
        encoded_credentials = auth_header.split(' ', 1)[1]
        decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
        username, password = decoded_credentials.split(':', 1)
        return (username, password)
    except Exception:
        return None

def require_auth(handler):
    """Decorator: enforce Basic Auth and attach credentials to request.auth_credentials."""
    @functools.wraps(handler)
    async def wrapper(request):
        auth = get_basic_auth(request)
        if not auth:
            return web.Response(status=401, headers={'WWW-Authenticate': 'Basic realm="HipoBridge"'})
        username, password = auth
        request['auth_credentials'] = (username, password)
        return await handler(request)
    return wrapper


@require_auth
async def search_patient(request):
    """Search patients by name, CNP, or patient code. Returns raw HipoData JSON."""
    search_term = request.query.get('q', '')
    if not search_term:
        return web_error_response("Search term is required")
    logger.info(f"Searching for patients with term: {search_term}")

    client = HipoClientPatientSearch(SERVICE_URL, request)
    parsed_data = await client.search(search_term)
    return web_json_response(parsed_data)

@require_auth
async def search_fhir_patient(request):
    """Search patients. Returns FHIR Patient resource or Bundle."""
    search_term = request.query.get('q', '')
    if not search_term:
        return web_fhir_response("Search term is required")
    logger.info(f"Searching for patients with term: {search_term}")

    client = HipoClientPatientSearch(SERVICE_URL, request)
    parsed_data = await client.search(search_term)

    if parsed_data.get('patient'):
        response = client.fhir_response(parsed_data)
    elif parsed_data.get('patients'):
        response = client.fhir_bundle_response(parsed_data, http_request=request)
    else:
        response = OperationOutcome.from_error(
            message="No patients found for the specified search criteria",
            code="not-found",
            severity="information"
        )

    return web_fhir_response(response)


@require_auth
async def get_patient(request):
    """Retrieve patient by ID. Returns raw HipoData JSON."""
    id = request.match_info.get('id')
    if not id:
        return web_error_response("Patient ID is required")
    logger.info(f"Retrieving patient with ID: {id}")

    client = HipoClientPatient(SERVICE_URL, request)

    debug_resp = await web_debug_response(client, request, id=id)
    if debug_resp is not None:
        return debug_resp

    parsed_data = await client.fetch_and_parse(id=id)
    return web_json_response(parsed_data)

@require_auth
async def get_fhir_patient(request):
    """Retrieve patient by ID. Returns FHIR Patient resource."""
    id = request.match_info.get('id')
    if not id:
        return web_fhir_response("Patient ID is required")
    logger.info(f"Retrieving patient with ID: {id}")

    client = HipoClientPatient(SERVICE_URL, request)
    response = await client.fetch_respond_fhir(id=id)
    return web_fhir_response(response)


@require_auth
async def search_request(request):
    """Search service requests for a patient. Returns raw HipoData JSON."""
    patient_id = request.query.get('patient', '')
    if not patient_id:
        return web_error_response("Patient ID is required")
    logger.info(f"Retrieving service requests for patient with ID: {patient_id}")

    exam_type = request.query.get('type')
    exam_region = request.query.get('region')
    exam_datetime = request.query.get('dt')

    client = HipoClientServiceRequestSearch(SERVICE_URL, request)
    parsed_data = await client.search(patient_id, type=exam_type, region=exam_region, dt=exam_datetime)
    return web_json_response(parsed_data)

@require_auth
async def search_fhir_service_request(request):
    """Search service requests for a patient. Returns FHIR ServiceRequest Bundle."""
    patient_id = request.query.get('patient', '')
    if not patient_id:
        return web_fhir_response("Patient ID is required")
    logger.info(f"Retrieving service requests for patient with ID: {patient_id}")

    exam_type = request.query.get('type')
    exam_region = request.query.get('region')
    exam_datetime = request.query.get('dt')

    client = HipoClientServiceRequestSearch(SERVICE_URL, request)
    parsed_data = await client.search(patient_id, type=exam_type, region=exam_region, dt=exam_datetime)
    response = client.fhir_bundle_response(parsed_data, http_request=request, patient_id=patient_id)
    return web_fhir_response(response)


@require_auth
async def get_request(request):
    """Retrieve service request by ID. Returns raw HipoData JSON."""
    id = request.match_info.get('id')
    if not id:
        return web_error_response("Service request ID is required")
    logger.info(f"Retrieving service request with ID: {id}")

    client = HipoClientServiceRequest(SERVICE_URL, request)

    debug_resp = await web_debug_response(client, request, id=id)
    if debug_resp is not None:
        return debug_resp

    parsed_data = await client.fetch_and_parse(id=id)
    return web_json_response(parsed_data)

@require_auth
async def get_fhir_service_request(request):
    """Retrieve service request by ID. Returns FHIR ServiceRequest resource.

    Accepts ?type=cerere to fetch from cerere.asp (full request metadata).
    Without the hint, fetches buletinRecoltari.asp (lab/imaging order content).
    """
    id = request.match_info.get('id')
    if not id:
        return web_fhir_response("Service request ID is required")
    logger.info(f"Retrieving service request with ID: {id}")

    if request.rel_url.query.get('type', '').lower() == 'cerere':
        cerere_client = HipoClientCerere(SERVICE_URL, request)
        return web_fhir_response(await cerere_client.fetch_respond_fhir(id=id))

    client = HipoClientServiceRequest(SERVICE_URL, request)
    response = await client.fetch_respond_fhir(id=id)
    return web_fhir_response(response)


@require_auth
async def get_study(request):
    """Retrieve imaging study by ID. Returns raw HipoData JSON."""
    id = request.match_info.get('id')
    if not id:
        return web_error_response("Imaging study ID is required")
    logger.info(f"Retrieving imaging study with ID: {id}")

    client = HipoClientImagingStudy(SERVICE_URL, request)

    debug_resp = await web_debug_response(client, request, id=id)
    if debug_resp is not None:
        return debug_resp

    parsed_data = await client.fetch_and_parse(id=id)
    return web_json_response(parsed_data)

@require_auth
async def get_fhir_imaging_study(request):
    """Retrieve imaging study by ID, following Hipocrate redirect chains. Returns FHIR ImagingStudy."""
    id = request.match_info.get('id')
    if not id:
        return web_fhir_response("Imaging study ID is required")
    logger.info(f"Retrieving imaging study with ID: {id}")

    client = HipoClientImagingStudy(SERVICE_URL, request)
    parsed_data = await client.fetch_and_parse(id=id)

    if parsed_data.get("status") != "error":
        cerere_client = HipoClientCerere(SERVICE_URL, request)
        cerere_data = await cerere_client.fetch_and_parse(id=id)
        justification = cerere_data.get("request.justification")
        if justification:
            parsed_data.store("request.justification", justification)

    response = client.fhir_response(parsed_data, id=id, http_request=request)
    return web_fhir_response(response)


@require_auth
async def get_report(request):
    """Retrieve diagnostic report by ID. Returns raw HipoData JSON."""
    id = request.match_info.get('id')
    if not id:
        return web_error_response("Diagnostic report ID is required")
    logger.info(f"Retrieving diagnostic report with ID: {id}")

    client = HipoClientDiagnosticReport(SERVICE_URL, request)

    debug_resp = await web_debug_response(client, request, id=id)
    if debug_resp is not None:
        return debug_resp

    parsed_data = await client.fetch_and_parse(id=id)
    return web_json_response(parsed_data)

@require_auth
async def get_fhir_diagnostic_report(request):
    """Retrieve diagnostic report by ID. Returns FHIR DiagnosticReport resource."""
    id = request.match_info.get('id')
    if not id:
        return web_fhir_response("Diagnostic report ID is required")
    logger.info(f"Retrieving diagnostic report with ID: {id}")

    client = HipoClientDiagnosticReport(SERVICE_URL, request)
    response = await client.fetch_respond_fhir(id=id)
    return web_fhir_response(response)


@require_auth
async def get_checkout(request):
    """Retrieve discharge summary by ID. Returns raw HipoData JSON."""
    id = request.match_info.get('id')
    if not id:
        return web_error_response("Checkout ID is required")
    logger.info(f"Retrieving checkout with ID: {id}")

    client = HipoClientCheckout(SERVICE_URL, request)

    debug_resp = await web_debug_response(client, request, id=id)
    if debug_resp is not None:
        return debug_resp

    parsed_data = await client.fetch_and_parse(id=id)
    return web_json_response(parsed_data)

@require_auth
async def get_checkin(request):
    """Retrieve admission record by ID. Returns raw HipoData JSON."""
    id = request.match_info.get('id')
    if not id:
        return web_error_response("Checkin ID is required")
    logger.info(f"Retrieving checkin with ID: {id}")
    client = HipoClientCheckin(SERVICE_URL, request)
    debug_resp = await web_debug_response(client, request, id=id)
    if debug_resp is not None:
        return debug_resp
    parsed_data = await client.fetch_and_parse(id=id)
    return web_json_response(parsed_data)

@require_auth
async def get_checkup(request):
    """Retrieve outpatient/emergency consultation by ID. Returns raw HipoData JSON."""
    id = request.match_info.get('id')
    if not id:
        return web_error_response("Checkup ID is required")
    logger.info(f"Retrieving checkup with ID: {id}")
    client = HipoClientCheckup(SERVICE_URL, request)
    debug_resp = await web_debug_response(client, request, id=id)
    if debug_resp is not None:
        return debug_resp
    parsed_data = await client.fetch_and_parse(id=id)
    return web_json_response(parsed_data)

@require_auth
async def get_presentation(request):
    """Retrieve outpatient/ER presentation by ID. Returns raw HipoData JSON."""
    id = request.match_info.get('id')
    if not id:
        return web_error_response("Presentation ID is required")
    logger.info(f"Retrieving presentation with ID: {id}")
    client = HipoClientPresentation(SERVICE_URL, request)
    debug_resp = await web_debug_response(client, request, id=id)
    if debug_resp is not None:
        return debug_resp
    parsed_data = await client.fetch_and_parse(id=id)
    return web_json_response(parsed_data)

@require_auth
async def get_request_patient(request):
    """Return patient and request metadata for a given request ID. Fetches cerere.asp."""
    id = request.match_info.get('id')
    if not id:
        return web_error_response("Request ID is required")
    client = HipoClientCerere(SERVICE_URL, request)
    debug_resp = await web_debug_response(client, request, id=id)
    if debug_resp is not None:
        return debug_resp
    parsed_data = await client.fetch_and_parse(id=id)
    return web_json_response(parsed_data)

@require_auth
async def get_schedule(request):
    """List imaging/lab requests. ?start_date=&end_date=&lab_id=&section_name=&patient_text=&refresh=1"""
    start_date   = request.rel_url.query.get('start_date') or request.rel_url.query.get('date')
    end_date     = request.rel_url.query.get('end_date')
    lab_id       = request.rel_url.query.get('lab_id')
    section_name = request.rel_url.query.get('section_name')
    patient_text = request.rel_url.query.get('patient_text')
    force        = request.rel_url.query.get('refresh') == '1'
    client = HipoClientSchedule(SERVICE_URL, request)
    debug_resp = await web_debug_response(client, request, start_date=start_date, end_date=end_date,
                                          lab_id=lab_id, patient_text=patient_text)
    if debug_resp is not None:
        return debug_resp
    parsed_data = await client.fetch_and_parse(start_date=start_date, end_date=end_date,
                                               lab_id=lab_id, section_name=section_name,
                                               patient_text=patient_text, force=force)
    return web_json_response(parsed_data)

@require_auth
async def get_fhir_schedule(request):
    """FHIR Bundle of ServiceRequest resources for the worklist. ?start_date=&end_date=&lab_id=&section_name=&patient_text=&refresh=1"""
    start_date   = request.rel_url.query.get('start_date') or request.rel_url.query.get('date')
    end_date     = request.rel_url.query.get('end_date')
    lab_id       = request.rel_url.query.get('lab_id')
    section_name = request.rel_url.query.get('section_name')
    patient_text = request.rel_url.query.get('patient_text')
    force        = request.rel_url.query.get('refresh') == '1'
    limit_raw    = request.rel_url.query.get('limit')
    limit        = int(limit_raw) if limit_raw and limit_raw.isdigit() else None
    client = HipoClientSchedule(SERVICE_URL, request)
    response = await client.fetch_respond_fhir(
        start_date=start_date, end_date=end_date,
        lab_id=lab_id, section_name=section_name, patient_text=patient_text,
        force=force, limit=limit, http_request=request)
    return web_fhir_response(response)

@require_auth
async def get_fhir_observation(request):
    """FHIR Bundle of Observations aggregated from all lab DiagnosticReports for a patient.
    ?patient={id}&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&refresh=1"""
    patient_id = request.rel_url.query.get('patient')
    if not patient_id:
        return web_fhir_response("patient parameter is required")
    start_date = request.rel_url.query.get('start_date')
    end_date   = request.rel_url.query.get('end_date')
    client = HipoClientObservationBundle(SERVICE_URL, request)
    response = await client.fetch_respond_fhir(
        patient_id=patient_id,
        start_date=start_date,
        end_date=end_date,
    )
    return web_fhir_response(response)

@require_auth
async def get_observation(request):
    """Raw HipoData aggregation of lab Observations for a patient. ?patient={id}&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD"""
    patient_id = request.rel_url.query.get('patient')
    if not patient_id:
        return web_error_response("patient parameter is required")
    start_date = request.rel_url.query.get('start_date')
    end_date   = request.rel_url.query.get('end_date')
    client = HipoClientObservationBundle(SERVICE_URL, request)
    parsed = await client.fetch_and_parse(
        patient_id=patient_id,
        start_date=start_date,
        end_date=end_date,
    )
    return web_json_response(parsed)

@require_auth
async def get_whoami(request):
    """Return the logged-in Hipocrate user identity. Returns raw HipoData JSON."""
    client = HipoClientWhoami(SERVICE_URL, request)
    debug_resp = await web_debug_response(client, request)
    if debug_resp is not None:
        return debug_resp
    parsed_data = await client.fetch_and_parse()
    parsed_data.store("hipocrate_url", SERVICE_URL)
    username, _ = request['auth_credentials']
    parsed_data.store("can_write_reports", username in _ALLOWED_RADIOLOGISTS)
    return web_json_response(parsed_data)

@require_auth
async def post_study_report(request):
    """Write a radiology report text for a request (cerere) via Hipocrate Rezultate.asp."""
    cerere_id = request.match_info['id']
    username, _ = request['auth_credentials']
    if username not in _ALLOWED_RADIOLOGISTS:
        return web.Response(status=403, text='Not authorised to write reports')
    try:
        body = await request.json()
        anl_id = (body.get('anl_id') or '').strip()
        text = (body.get('text') or '').strip()
    except Exception:
        return web.Response(status=400, text='Invalid JSON body')
    if not anl_id or not text:
        return web.Response(status=400, text='anl_id and text are required')
    client = HipoClientReportWrite(SERVICE_URL, request)
    result = await client.write(cerere_id, anl_id, text)
    return web_json_response(result)

@require_auth
async def post_report_validate(request):
    """Validate or devalidate a radiology report result."""
    cerere_id = request.match_info['id']
    username, _ = request['auth_credentials']
    if username not in _ALLOWED_RADIOLOGISTS:
        return web.Response(status=403, text='Not authorised to validate reports')
    try:
        body = await request.json()
        anl_id = (body.get('anl_id') or '').strip()
        id_grup = str(body.get('id_grup', '0'))
        validated = bool(body.get('validated'))
    except Exception:
        return web.Response(status=400, text='Invalid JSON body')
    if not anl_id:
        return web.Response(status=400, text='anl_id is required')
    client = HipoClientReportValidate(SERVICE_URL, request)
    result = await client.validate(cerere_id, anl_id, id_grup, validated)
    return web_json_response(result)

@require_auth
async def post_study_perform(request):
    """Mark a radiology exam as performed by setting DataEfectuarii on cerere.asp."""
    cerere_id = request.match_info['id']
    username, _ = request['auth_credentials']
    if username not in _ALLOWED_RADIOLOGISTS:
        return web.Response(status=403, text='Not authorised to perform exams')
    try:
        body = await request.json()
        performed_at = (body.get('performed_at') or '').strip() or None
    except Exception:
        performed_at = None
    client = HipoClientCererePerform(SERVICE_URL, request)
    result = await client.perform(cerere_id, performed_at)
    return web_json_response(result)

@require_auth
async def post_logout(request):
    """Close the user's Hipocrate session held by the bridge."""
    username, _ = request['auth_credentials']
    await user_session_manager.close_user_session(username)
    return web_json_response(HipoData(status="success", message=""))

@require_auth
async def debug_passthrough(request):
    """Fetch any Hipocrate path for debugging. ?path=/files/checkup.asp?cuid=..."""
    path = request.query.get('path', '')
    if not path:
        return web.Response(text='Missing ?path=', status=400)
    client = HipoClient(SERVICE_URL, request)
    html, err = await client.get_page(path)
    if err:
        return web.Response(text=f'Error: {err}', status=500)
    return web.Response(text=html, content_type='text/html')

@require_auth
async def get_fhir_encounter(request):
    """Retrieve encounter by ID.

    Accepts an optional ?type=checkout|checkin|checkup|presentation hint so the
    caller can skip straight to the right scraper.  Without the hint the handler
    falls through checkout → checkin → presentation as before.
    """
    id = request.match_info.get('id')
    if not id:
        return web_fhir_response("Encounter ID is required")
    enc_type = request.rel_url.query.get('type', '').lower()
    logger.info(f"Retrieving encounter {id} (type={enc_type or 'auto'})")

    if enc_type == 'presentation':
        presentation_client = HipoClientPresentation(SERVICE_URL, request)
        return web_fhir_response(await presentation_client.fetch_respond_fhir(id=id))

    if enc_type == 'checkin':
        checkin_client = HipoClientCheckin(SERVICE_URL, request)
        checkin_data = await checkin_client.fetch_and_parse(id=id)
        return web_fhir_response(checkin_client.fhir_response(checkin_data, id=id))

    if enc_type == 'checkout':
        checkout_client = HipoClientCheckout(SERVICE_URL, request)
        checkout_data = await checkout_client.fetch_and_parse(id=id)
        return web_fhir_response(checkout_client.fhir_response(checkout_data, id=id))

    if enc_type == 'checkup':
        checkup_client = HipoClientCheckup(SERVICE_URL, request)
        checkup_data = await checkup_client.fetch_and_parse(id=id)
        return web_fhir_response(checkup_client.fhir_response(checkup_data, id=id))

    # No hint — try checkout (completed discharge) first
    checkout_client = HipoClientCheckout(SERVICE_URL, request)
    checkout_data = await checkout_client.fetch_and_parse(id=id)
    checkout_name = (checkout_data.get("patient.name") or "").replace("-", "").replace(" ", "")
    if checkout_data.get("status") != "error" and checkout_name:
        return web_fhir_response(checkout_client.fhir_response(checkout_data, id=id))

    logger.info(f"Checkout {id} not found or empty — trying checkin")
    checkin_client = HipoClientCheckin(SERVICE_URL, request)
    checkin_data = await checkin_client.fetch_and_parse(id=id)
    if checkin_data.get("status") != "error" and checkin_data.get("checkin.diagnosis"):
        return web_fhir_response(checkin_client.fhir_response(checkin_data, id=id))

    logger.info(f"Checkin {id} not found or empty — trying presentation")
    presentation_client = HipoClientPresentation(SERVICE_URL, request)
    return web_fhir_response(await presentation_client.fetch_respond_fhir(id=id))


async def serve_spec(request):
    """Serve spec.json as OpenAPI specification, updating the server URL dynamically."""
    logger.info("GET /fhir/spec endpoint accessed")

    spec_path = os.path.join(os.path.dirname(__file__), 'spec.json')
    try:
        with open(spec_path, 'r') as f:
            spec = json.load(f)
        spec["servers"][0]["url"] = f"{request.scheme}://{request.host}"
        return web.json_response(spec)
    except FileNotFoundError:
        return web_error_response("Specification file not found", 500)
    except json.JSONDecodeError as e:
        logger.error(f"spec.json parse error: {e}")
        return web_error_response("Error parsing specification file", 500)


async def serve_fhir_analysis_types(request):
    """Serve FHIR CodeSystem resource listing the Hipocrate analysis types."""
    concepts = [
        {"code": code, "display": details["display"], "definition": details["definition"]}
        for code, details in ANALYSIS_TYPES.items()
    ]

    code_system = Resource(
        resourceType="CodeSystem",
        id="analysis-types",
        url=f"{request.scheme}://{request.host}/fhir/CodeSystem/analysis-types",
        version="1.0.0",
        name="HipocrateAnalysisTypes",
        title="Hipocrate Analysis Types",
        status="active",
        experimental=False,
        date=datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        publisher="Hipocrate",
        description="Code system for analysis types used by the Hipocrate",
        caseSensitive=True,
        content="complete",
        concept=concepts
    )

    return web_fhir_response(code_system)


async def serve_fhir_metadata(request):
    """Serve FHIR CapabilityStatement for this server."""
    logger.info("GET /fhir/Metadata endpoint accessed")

    capability_statement = Resource(
        resourceType="CapabilityStatement",
        id="hipobridge-fhir-capability-statement",
        url=f"{request.scheme}://{request.host}/fhir/Metadata",
        version="1.0.0",
        name="HipoBridgeFHIRCapabilityStatement",
        title="HipoBridge FHIR Capability Statement",
        status="active",
        experimental=False,
        date=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'),
        publisher="HipoBridge",
        description="This is the FHIR capability statement for the HipoBridge FHIR API",
        kind="instance",
        software={
            "name": "HipoBridge",
            "version": "1.0.0"
        },
        fhirVersion="4.0.1",
        format=["application/fhir+json", "application/json"],
        rest=[
            {
                "mode": "server",
                "resource": [
                    {
                        "type": "Patient",
                        "interaction": [
                            {"code": "read"},
                            {"code": "search-type"}
                        ]
                    },
                    {
                        "type": "ServiceRequest",
                        "interaction": [
                            {"code": "read"},
                            {"code": "search-type"}
                        ]
                    },
                    {
                        "type": "DiagnosticReport",
                        "interaction": [
                            {"code": "read"}
                        ]
                    },
                    {
                        "type": "ImagingStudy",
                        "interaction": [
                            {"code": "read"}
                        ]
                    },
                    {
                        "type": "Encounter",
                        "interaction": [
                            {"code": "read"}
                        ]
                    }
                ]
            }
        ]
    )

    return web_fhir_response(capability_statement)


async def serve_md2html(request):
    """Convert markdown text to HTML. Accepts JSON body with 'text' field."""
    try:
        data = await request.json()
        markdown_text = data.get('text', '')
        if not isinstance(markdown_text, str):
            return web_error_response("'text' field must be a string")
        html_content = markdown_to_html(markdown_text)
        return web_json_response({
            "status": "success",
            "html": html_content
        })
    except json.JSONDecodeError:
        return web_error_response("Invalid JSON data")
    except Exception as e:
        return web_error_response("Markdown conversion failed", 500, {"exception": str(e)})


@require_auth
async def serve_validate_cnp(request):
    """Validate a Romanian CNP and return parsed demographic data."""
    cnp = request.query.get('id')
    if not cnp:
        return web_error_response("CNP is required")
    logger.info(f"Validating CNP: {cnp}")

    parsed_data = parse_cnp(cnp)

    response_data = {
        "status": "success",
        "cnp": cnp,
        "valid": parsed_data.get("valid", False)
    }

    if parsed_data.get("valid"):
        response_data.update({
            "gender": parsed_data.get("gender"),
            "birth_date": parsed_data.get("birth_date"),
            "county_code": parsed_data.get("county_code"),
            "county_name": parsed_data.get("county_name"),
            "serial": parsed_data.get("serial"),
            "control_digit": parsed_data.get("control_digit")
        })

    return web_json_response(response_data)


async def serve_web_page(request):
    """Serve the SPA. Auth is handled client-side via JS login dialog."""
    return web.FileResponse(os.path.join(os.path.dirname(__file__), 'static', 'main.html'))


def web_error_response(message: str, status_code: int = 400, details: Dict[str, Any] = None) -> web.Response:
    """Return a standardized JSON error response."""
    if status_code >= 500:
        logger.error(message)
    else:
        logger.warning(message)
    response_data = {"status": "error", "message": message}
    if details:
        response_data["details"] = details
    return web.json_response(response_data, status=status_code)


def web_json_response(data: Dict[str, Any]) -> web.Response:
    """Return 200 for successful HipoData, 404 for not-found, 500 for errors."""
    s = data.get("status")
    if s == "success":
        status = 200
    elif s == "error":
        msg = data.get("message", "")
        # Distinguish parse/upstream failures (500) from not-found (404)
        status = 404 if "not found" in msg.lower() else 500
    else:
        status = 200
    return web.json_response(data, status=status)


async def web_debug_response(client, request, **kwargs) -> web.Response:
    """Return raw Hipocrate HTML when ?debug=page is set, else None."""
    if request.query.get('debug') == 'page':
        result = await client.debug_page(**kwargs)
        return web.Response(text=result, content_type="text/html")
    return None


def web_fhir_response(data) -> web.Response:
    """Return a FHIR-typed JSON response.

    Strings are wrapped in OperationOutcome (400 — caller omitted a required param).
    Resource objects are serialized via to_dict(). HTTP status is derived from
    OperationOutcome issue code: 'not-found' → 404, 'information' severity → 200,
    other errors → 500, warnings → 400.
    """
    FHIR_CONTENT_TYPE = 'application/fhir+json'

    if isinstance(data, str):
        operation_outcome = OperationOutcome.from_error(message=data, code="required", severity="error")
        return web.json_response(operation_outcome.to_dict(), status=400,
                                 content_type=FHIR_CONTENT_TYPE)

    if hasattr(data, 'to_dict'):
        response_data = data.to_dict()
    else:
        response_data = data

    status_code = 200
    if isinstance(response_data, dict) and response_data.get('resourceType') == 'OperationOutcome':
        issues = response_data.get('issue', [])
        if any(i.get('code') == 'not-found' for i in issues):
            status_code = 404
        elif any(i.get('severity') in ['error', 'fatal'] for i in issues):
            status_code = 500
        elif any(i.get('severity') == 'warning' for i in issues):
            status_code = 400
        # 'information' severity (e.g. search returning zero results) stays 200

    return web.json_response(response_data, status=status_code,
                             content_type=FHIR_CONTENT_TYPE)


@require_auth
async def get_cache_stats(request):
    """Return filesystem cache statistics as JSON."""
    if url_cache.fs_cache is None:
        return web.json_response({'enabled': False})
    return web.json_response({'enabled': True, **url_cache.fs_cache.stats()})


@require_auth
async def post_cache_cleanup(request):
    """Trigger a filesystem cache cleanup and return deleted/freed counts."""
    if url_cache.fs_cache is None:
        return web.json_response({'enabled': False, 'deleted': 0, 'freed_bytes': 0})
    result = await asyncio.get_event_loop().run_in_executor(
        None, url_cache.fs_cache.cleanup
    )
    return web.json_response({'enabled': True, **result})


def load_config():
    """Load hipobridge.cfg then overlay local.cfg if present."""
    config = configparser.ConfigParser()
    config.read_dict(DEFAULT_CONFIG)

    if os.path.exists('hipobridge.cfg'):
        logger.info("Loading hipobridge.cfg configuration")
        config.read('hipobridge.cfg')
    else:
        logger.info("hipobridge.cfg not found, using default configuration")

    if os.path.exists('local.cfg'):
        logger.info("Loading local.cfg configuration (overrides hipobridge.cfg)")
        config.read('local.cfg')

    return config

_wl_server = None   # set by init_app; used by on_cleanup for graceful DICOM shutdown

async def _periodic_cache_cleanup():
    """Background task: run FilesystemCache.cleanup() once at startup then every 24 h."""
    while True:
        if url_cache.fs_cache is not None:
            try:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, url_cache.fs_cache.cleanup
                )
                logger.info(f"Periodic cache cleanup: {result['deleted']} files deleted, {result['freed_bytes']} bytes freed")
            except Exception as exc:
                logger.warning(f"Periodic cache cleanup failed: {exc}")
        await asyncio.sleep(86400)

async def on_cleanup(app):
    """Graceful shutdown: stop DICOM SCP then close Hipocrate HTTP sessions."""
    logger.info("Application cleanup")
    if _wl_server is not None:
        await asyncio.get_event_loop().run_in_executor(None, _wl_server.shutdown)
    await user_session_manager.close_all_sessions()

async def init_app(no_disk_cache: bool = False, no_worklist: bool = False,
                   port: int = None, host: str = None, service_url: str = None):
    """Load config, wire up routes and lifecycle handlers, return the configured app."""
    global SERVICE_URL, _PORT, _HOST, _ALLOWED_RADIOLOGISTS
    config = load_config()
    SERVICE_URL = service_url or config.get('hipocrate', 'service_url')
    _PORT = port or config.getint('server', 'port')
    _HOST = host or config.get('server', 'host')
    _ALLOWED_RADIOLOGISTS = {
        u.strip() for u in config.get('radiology', 'allowed_radiologists').split(',') if u.strip()
    }
    logger.info(f"Service URL: {SERVICE_URL}")

    cache_dir = config.get('cache', 'dir').strip()
    if cache_dir and not no_disk_cache:
        cache_ttl = config.getint('cache', 'ttl')
        cache_max_age = config.getint('cache', 'max_age_days')
        url_cache.fs_cache = FilesystemCache(cache_dir, ttl=cache_ttl, max_age_days=cache_max_age)
        asyncio.get_event_loop().create_task(_periodic_cache_cleanup())
    elif no_disk_cache and cache_dir:
        logger.info("Persistent filesystem cache disabled (--no-disk-cache)")
    else:
        logger.info("Persistent filesystem cache disabled (no cache.dir configured)")

    app = web.Application()
    app.router.add_get('/', serve_web_page)
    app.router.add_get('/api/patient', search_patient)
    app.router.add_get('/api/patient/{id}', get_patient)
    app.router.add_get('/api/request', search_request)
    app.router.add_get('/api/request/{id}', get_request)
    app.router.add_get('/api/study/{id}', get_study)
    app.router.add_get('/api/report/{id}', get_report)
    app.router.add_get('/api/checkout/{id}', get_checkout)
    app.router.add_get('/api/checkin/{id}', get_checkin)
    app.router.add_get('/api/checkup/{id}', get_checkup)
    app.router.add_get('/api/presentation/{id}', get_presentation)
    app.router.add_get('/api/request/{id}/patient', get_request_patient)
    app.router.add_post('/api/request/{id}/report', post_study_report)
    app.router.add_post('/api/request/{id}/validate', post_report_validate)
    app.router.add_post('/api/request/{id}/perform', post_study_perform)
    app.router.add_get('/api/schedule', get_schedule)
    app.router.add_get('/fhir/Schedule', get_fhir_schedule)
    app.router.add_get('/api/whoami', get_whoami)
    app.router.add_post('/api/logout', post_logout)
    app.router.add_get('/api/debug', debug_passthrough)
    app.router.add_get('/api/cache/stats', get_cache_stats)
    app.router.add_post('/api/cache/cleanup', post_cache_cleanup)
    app.router.add_get('/fhir/Patient', search_fhir_patient)
    app.router.add_get('/fhir/Patient/{id}', get_fhir_patient)
    app.router.add_get('/fhir/ServiceRequest', search_fhir_service_request)
    app.router.add_get('/fhir/ServiceRequest/{id}', get_fhir_service_request)
    app.router.add_get('/fhir/ImagingStudy/{id}', get_fhir_imaging_study)
    app.router.add_get('/fhir/DiagnosticReport/{id}', get_fhir_diagnostic_report)
    app.router.add_get('/fhir/Encounter/{id}', get_fhir_encounter)
    app.router.add_get('/api/observation', get_observation)
    app.router.add_get('/fhir/Observation', get_fhir_observation)
    app.router.add_get('/fhir/ValueSet/cnp', serve_validate_cnp)
    app.router.add_post('/fhir/md2html', serve_md2html)
    app.router.add_get('/fhir/CodeSystem/analysis-types', serve_fhir_analysis_types)
    app.router.add_get('/fhir/spec', serve_spec)
    app.router.add_get('/fhir/Metadata', serve_fhir_metadata)
    app.router.add_static('/static/', path=os.path.join(os.path.dirname(__file__), 'static'), name='static')

    app.on_cleanup.append(on_cleanup)

    global _wl_server
    if no_worklist:
        logger.info("DICOM worklist disabled (--no-worklist)")
    else:
        _wl_server = start_worklist(SERVICE_URL)

    return app

# Module-level defaults — overridden by init_app() from the config files
SERVICE_URL: str = DEFAULT_CONFIG['hipocrate']['service_url']
_PORT: int = int(DEFAULT_CONFIG['server']['port'])
_HOST: str = DEFAULT_CONFIG['server']['host']
_ALLOWED_RADIOLOGISTS: set = set()

if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description='HipoBridge scraping proxy server')
    parser.add_argument(
        '--log-level', metavar='LEVEL',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Override log level (default: INFO or $LOG_LEVEL)'
    )
    parser.add_argument(
        '--port', type=int, metavar='PORT',
        help='Override server port (default: from config)'
    )
    parser.add_argument(
        '--host', metavar='HOST',
        help='Override bind address (default: from config)'
    )
    parser.add_argument(
        '--service-url', metavar='URL',
        help='Override Hipocrate base URL (default: from config)'
    )
    parser.add_argument(
        '--no-disk-cache', action='store_true',
        help='Disable persistent filesystem cache even if cache.dir is configured'
    )
    parser.add_argument(
        '--no-worklist', action='store_true',
        help='Disable DICOM worklist SCP even if worklist.cfg is present'
    )
    args = parser.parse_args()

    if args.log_level:
        logging.getLogger().setLevel(getattr(logging, args.log_level))

    async def _main():
        global SERVICE_URL, _PORT, _HOST
        app = await init_app(
            no_disk_cache=args.no_disk_cache,
            no_worklist=args.no_worklist,
            port=args.port,
            host=args.host,
            service_url=args.service_url,
        )
        logger.info(f"Starting HipoBridge server on {_HOST}:{_PORT}")
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, _HOST, _PORT)
        await site.start()
        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()

    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
