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
from hipoclient import HipoClient, HipoClientPatient, HipoClientPatientSearch, HipoClientImagingStudy, HipoClientDiagnosticReport, HipoClientServiceRequest, HipoClientServiceRequestSearch, HipoClientCheckout
from hipoclient import user_session_manager
from hipodata import HipoData

from extractors import parse_cnp
from markdown import markdown_to_html

logging.basicConfig(
    level=logging.DEBUG,
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
    }
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
        request.auth_credentials = (username, password)
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

    if 'patient' in parsed_data:
        response = client.fhir_response(parsed_data)
    elif 'patients' in parsed_data and len(parsed_data['patients']) > 0:
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
    if debug_resp:
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
    full_data = request.query.get('full', 'no').lower() == 'yes'

    client = HipoClientServiceRequestSearch(SERVICE_URL, request)
    parsed_data = await client.search(patient_id, type=exam_type, region=exam_region, dt=exam_datetime, full=full_data)
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
    full_data = request.query.get('full', 'no').lower() == 'yes'

    client = HipoClientServiceRequestSearch(SERVICE_URL, request)
    parsed_data = await client.search(patient_id, type=exam_type, region=exam_region, dt=exam_datetime, full=full_data)
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
    if debug_resp:
        return debug_resp

    parsed_data = await client.fetch_and_parse(id=id)
    return web_json_response(parsed_data)

@require_auth
async def get_fhir_service_request(request):
    """Retrieve service request by ID. Returns FHIR ServiceRequest resource."""
    id = request.match_info.get('id')
    if not id:
        return web_fhir_response("Service request ID is required")
    logger.info(f"Retrieving service request with ID: {id}")

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
    if debug_resp:
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
    response = await client.fetch_respond_fhir(id=id)
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
    if debug_resp:
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
    if debug_resp:
        return debug_resp

    parsed_data = await client.fetch_and_parse(id=id)
    return web_json_response(parsed_data)

@require_auth
async def get_fhir_encounter(request):
    """Retrieve encounter (discharge summary) by ID. Returns FHIR Encounter resource."""
    id = request.match_info.get('id')
    if not id:
        return web_fhir_response("Encounter ID is required")
    logger.info(f"Retrieving encounter with ID: {id}")

    client = HipoClientCheckout(SERVICE_URL, request)
    response = await client.fetch_respond_fhir(id=id)
    return web_fhir_response(response)


async def serve_spec(request):
    """Serve spec.json as OpenAPI specification, updating the server URL dynamically."""
    logger.info("GET /fhir/spec endpoint accessed")

    try:
        with open('spec.json', 'r') as f:
            spec = json.load(f)
        spec["servers"][0]["url"] = f"{request.scheme}://{request.host}"
        return web.json_response(spec)
    except FileNotFoundError:
        return web_error_response("Specification file not found", 500)
    except json.JSONDecodeError as e:
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


@require_auth
async def serve_web_page(request):
    """Serve the SPA after verifying Hipocrate credentials are valid."""
    username, password = request.auth_credentials

    client = HipoClient(SERVICE_URL, request)
    session, login_success = await client.get_authenticated_session(username, password)

    if not login_success:
        return web.Response(status=401, headers={'WWW-Authenticate': 'Basic realm="HipoBridge"'})

    return web.FileResponse('static/main.html')


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
    """Return 200 for successful HipoData, 404 otherwise."""
    status = 200 if data.get("status") == "success" else 404
    return web.json_response(data, status=status)


async def web_debug_response(client, request, **kwargs) -> web.Response:
    """Return raw Hipocrate HTML when ?debug=page is set, else None."""
    if request.query.get('debug') == 'page':
        result = await client.debug_page(**kwargs)
        return web.Response(body=result, content_type="text/html")
    return None


def web_fhir_response(data) -> web.Response:
    """Return a FHIR-typed JSON response.

    Strings are wrapped in OperationOutcome (500). Resource objects are serialized
    via to_dict(). Status code is derived from OperationOutcome severity.
    """
    if isinstance(data, str):
        operation_outcome = OperationOutcome.from_error(message=data, code="processing", severity="error")
        response_data = operation_outcome.to_dict()
        return web.json_response(response_data, status=500)

    if hasattr(data, 'to_dict'):
        response_data = data.to_dict()
    else:
        response_data = data

    status_code = 200
    if isinstance(response_data, dict):
        if response_data.get('resourceType') == 'OperationOutcome':
            if any(issue.get('severity') in ['error', 'fatal']
                   for issue in response_data.get('issue', [])):
                status_code = 500
            elif any(issue.get('severity') == 'warning'
                     for issue in response_data.get('issue', [])):
                status_code = 400
        elif response_data.get('status') == 'error':
            status_code = 404

    return web.json_response(response_data, status=status_code)


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

async def on_startup(app):
    logger.info("Application startup")

async def on_cleanup(app):
    """Close all user HTTP sessions on shutdown."""
    logger.info("Application cleanup")
    await user_session_manager.close_all_sessions()

async def init_app():
    """Wire up routes and lifecycle handlers, return the configured app."""
    logger.info("Initializing web application")

    app = web.Application()
    app.router.add_get('/', serve_web_page)
    app.router.add_get('/api/patient', search_patient)
    app.router.add_get('/api/patient/{id}', get_patient)
    app.router.add_get('/api/request', search_request)
    app.router.add_get('/api/request/{id}', get_request)
    app.router.add_get('/api/study/{id}', get_study)
    app.router.add_get('/api/report/{id}', get_report)
    app.router.add_get('/api/checkout/{id}', get_checkout)
    app.router.add_get('/fhir/Patient', search_fhir_patient)
    app.router.add_get('/fhir/Patient/{id}', get_fhir_patient)
    app.router.add_get('/fhir/ServiceRequest', search_fhir_service_request)
    app.router.add_get('/fhir/ServiceRequest/{id}', get_fhir_service_request)
    app.router.add_get('/fhir/ImagingStudy/{id}', get_fhir_imaging_study)
    app.router.add_get('/fhir/DiagnosticReport/{id}', get_fhir_diagnostic_report)
    app.router.add_get('/fhir/Encounter/{id}', get_fhir_encounter)
    app.router.add_get('/fhir/ValueSet/cnp', serve_validate_cnp)
    app.router.add_post('/fhir/md2html', serve_md2html)
    app.router.add_get('/fhir/CodeSystem/analysis-types', serve_fhir_analysis_types)
    app.router.add_get('/fhir/spec', serve_spec)
    app.router.add_get('/fhir/Metadata', serve_fhir_metadata)
    app.router.add_static('/static/', path='static', name='static')

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    return app

config = load_config()
SERVICE_URL = config.get('hipocrate', 'service_url')
PORT = config.getint('server', 'port')
HOST = config.get('server', 'host')

if __name__ == "__main__":
    logger.info(f"Starting HipoBridge server on {HOST}:{PORT}")
    web.run_app(init_app(), host=HOST, port=PORT)
