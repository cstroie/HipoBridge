#!/usr/bin/env python3
"""
HipoBridge - FHIR Bridge for Hipocrate Medical System

This application provides a FHIR-compatible API bridge to access patient data
from the Hipocrate medical system. It exposes endpoints for patient search,
retrieval, observations, diagnostic reports, and encounters.

Key Features:
- FHIR-compatible REST API
- Patient search by name, CNP, or patient code
- Patient data retrieval with checkin/checkout IDs
- Observation (analysis) listing and details
- Diagnostic report retrieval with redirect handling
- Encounter (checkout) information
- CNP validation and parsing
- Web interface for patient analysis
- Configuration via file with environment variable overrides

Configuration:
- Server settings (host, port) in hipp.cfg
- Hipocrate service URL in hipp.cfg
- Credentials via HYP_USER and HYP_PASS environment variables
- Local overrides in local.cfg (optional)

Author: Costin Stroie <costinstroie@eridu.eu.org>
License: GPL-3.0
Version: 1.0.0
"""
import os
import asyncio
import aiohttp
from aiohttp import web
from typing import Dict, Any, Optional, List
import json
import logging
import re
from bs4 import BeautifulSoup
import html
from datetime import datetime, timedelta
import configparser
import base64

# Import FHIR classes
from fhir import ServiceRequest as FHIRServiceRequest, CodeableConcept, Coding, Reference, CodeableReference, Condition, Patient as FHIRPatient

from hipo import ANALYSIS_TYPES
from hipo import HipoClient, HipoClientPatient, HipoClientPatientSearch, HipoClientImagingStudy, HipoClientDiagnosticReport, HipoClientServiceRequest, HipoClientServiceRequestSearch, HipoClientCheckout
from hipo import HipoData, user_session_manager

from extractors import parse_cnp

from markdown import html_to_markdown, markdown_to_html

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)8s | %(message)s'
)
logger = logging.getLogger('HipoBridge')

# Default configuration
DEFAULT_CONFIG = {
    'server': {
        'port': '44660',
        'host': '0.0.0.0'
    },
    'hipocrate': {
        'service_url': 'http://127.0.0.1/hipocrate'
    }
}



# Authentication helpers
# ###########################################################################


def get_basic_auth(request):
    """Extract basic auth credentials from request.

    Args:
        request: The incoming HTTP request

    Returns:
        Tuple of (username, password) or None if not found
    """
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
    """Decorator to require basic authentication for endpoints."""
    async def wrapper(request):
        # Get credentials from basic auth
        auth = get_basic_auth(request)
        if not auth:
            return web.Response(status=401, headers={'WWW-Authenticate': 'Basic realm="HipoBridge"'})
        # Extract username and password
        username, password = auth
        # Add credentials to request for use in handler
        request.auth_credentials = (username, password)
        # Call the original handler
        return await handler(request)
    # End of wrapper function
    return wrapper



# Endpoints
# ###########################################################################


@require_auth
async def search_patient(request):
    """Search for patients by name, CNP, or patient code.

    Searches for patients in the Hipocrate service using various search criteria
    and returns matching patient information.

    Args:
        request: The incoming HTTP request with 'q' query parameter for search term
                 and basic auth credentials for authentication

    Returns:
        JSON response with patient search results or error information
    """
    # Get search parameter from query string
    search_term = request.query.get('q', '')
    if not search_term:
        return error_response("Search term is required")
    logger.info(f"Searching for patients with term: {search_term}")

    try:
        # Create a new HipoClient instance with credentials
        client = HipoClientPatientSearch(SERVICE_URL, request)

        # Retrieve and parse the page
        parsed_data = await client.search(search_term)

        # Return the response
        return json_response(parsed_data)

    except Exception as e:
        return error_response("Patient retrieval failed", 500, {"exception": str(e)})

@require_auth
async def search_fhir_patient(request):
    """Search for patients and return FHIR-formatted results.

    Searches for patients in the Hipocrate service and returns results
    in FHIR Patient resource format.

    Args:
        request: The incoming HTTP request with 'q' query parameter for search term
                 and basic auth credentials for authentication

    Returns:
        JSON response with FHIR Patient resources or error information
    """
    # Get search parameter from query string
    search_term = request.query.get('q', '')
    if not search_term:
        return error_response("Search term is required")
    logger.info(f"Searching for patients with term: {search_term}")

    try:
        # Create a new HipoClient instance with credentials
        client = HipoClientPatientSearch(SERVICE_URL, request)

        # Retrieve and parse the page
        parsed_data = await client.search(search_term)

        # Check if there is one patient or there are more in response
        if 'patient' in parsed_data:
            # Convert parsed data to FHIR resource
            parsed_data['fhir'] = client.fhir_response(parsed_data)
        elif 'patients' in parsed_data and len(parsed_data['patients']) > 0:
            # Convert multiple patients to FHIR Bundle
            bundle = {
                "resourceType": "Bundle",
                "type": "searchset",
                "total": len(parsed_data['patients']),
                "entry": []
            }
            for patient_id, patient_name in parsed_data['patients'].items():
                # Add entry to bundle
                bundle["entry"].append({
                    "resource": client.fhir_response(HipoData(patient={'name': patient_name, 'id': patient_id}))
                })
            parsed_data['fhir'] = bundle
        else:
            parsed_data['fhir'] = {}
        
        # Return the response
        return json_response(parsed_data)

    except Exception as e:
        return error_response("Patient retrieval failed", 500, {"exception": str(e)})


@require_auth
async def get_patient(request):
    """Retrieve patient information by ID.

    Gets detailed patient information from the Hipocrate service including
    personal data, contact information, and related encounter IDs.

    Args:
        request: The incoming HTTP request with 'id' path parameter for patient ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with patient data or error information
    """
    # Extract patient ID from path
    id = request.match_info.get('id')
    if not id:
        return error_response("Patient ID is required")
    logger.info(f"Retrieving patient with ID: {id}")

    try:
        # Create a new HipoClient instance with credentials
        client = HipoClientPatient(SERVICE_URL, request)

        # Retrieve and parse the page
        parsed_data = await client.fetch_and_parse(id=id)

        # Return the response
        return json_response(parsed_data)

    except Exception as e:
        return error_response("Patient retrieval failed", 500, {"exception": str(e)})

@require_auth
async def get_fhir_patient(request):
    """Retrieve patient information by ID.

    Gets patient information from the Hipocrate service and extracts
    associated admission and discharge IDs.

    Args:
        request: The incoming HTTP request with 'id' query parameter for patient ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with patient data or error information
    """
    # Get patient ID from request path
    id = request.match_info.get('id')
    if not id:
        return error_response("Patient ID is required")
    logger.info(f"Retrieving patient with ID: {id}")

    try:
        # Create a new HipoClient instance with credentials
        client = HipoClientPatient(SERVICE_URL, request)

        # Retrieve and parse the page, then convert to FHIR resource
        response = await client.fetch_repond_fhir(id=id)

        # Return the response
        return json_response(response)

    except Exception as e:
        return error_response("Patient retrieval failed", 500, {"exception": str(e)})


@require_auth
async def search_request(request):
    """Search for service requests for a specific patient.

    Gets service requests (medical examinations, lab tests, imaging studies) 
    for a patient from the Hipocrate service.

    Args:
        request: The incoming HTTP request with 'patient' query parameter for patient ID
                 and optional 'type', 'region', 'dt', and 'full' parameters
                 and basic auth credentials for authentication

    Returns:
        JSON response with service request data or error information
    """
    # Get search parameter from query string
    patient_id = request.query.get('patient', '')
    if not patient_id:
        return error_response("Patient ID is required")
    logger.info(f"Retrieving service requests for patient with ID: {patient_id}")

    # Get optional parameters
    exam_type = request.query.get('type')
    exam_region = request.query.get('region')
    exam_datetime = request.query.get('dt')
    full_data = request.query.get('full', 'no').lower() == 'yes'

    try:
        # Create a new HipoClient instance with credentials
        client = HipoClientServiceRequestSearch(SERVICE_URL, request)

        # Retrieve and parse the page
        parsed_data = await client.search(patient_id, type=exam_type, region=exam_region, dt=exam_datetime, full=full_data)

        # Return the response
        return json_response(parsed_data)

    except Exception as e:
        return error_response("Service requests retrieval failed", 500, {"exception": str(e)})

@require_auth
async def search_fhir_service_request(request):
    """Retrieve patient information by ID.

    Gets patient information from the Hipocrate service and extracts
    associated admission and discharge IDs.

    Args:
        request: The incoming HTTP request with 'id' query parameter for patient ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with patient data or error information
    """
    # Get search parameter from query string
    patient_id = request.query.get('patient', '')
    if not patient_id:
        return error_response("Patient ID is required")
    logger.info(f"Retrieving service requests for patient with ID: {patient_id}")

    # Get optional parameters
    exam_type = request.query.get('type')
    exam_region = request.query.get('region')
    exam_datetime = request.query.get('dt')
    full_data = request.query.get('full', 'no').lower() == 'yes'

    try:
        # Create a new HipoClient instance with credentials
        client = HipoClientServiceRequestSearch(SERVICE_URL, request)

        # Retrieve and parse the page
        parsed_data = await client.search(patient_id, type=exam_type, region=exam_region, dt=exam_datetime, full=full_data)

        # Check if there are more in response
        if 'requests' in parsed_data and len(parsed_data['requests']) > 0:
            # Convert multiple patients to FHIR Bundle
            bundle = {
                "resourceType": "Bundle",
                "type": "searchset",
                "total": len(parsed_data['requests']),
                "entry": []
            }

            for req in parsed_data['requests']:
                # Create FHIR ServiceRequest using the FHIR class
                fhir_service_request = FHIRServiceRequest(
                    id=req["id"],
                    status="active",
                    intent="order",
                    priority="urgent" if req.get("is_urgent") else "routine"
                )
                
                # Add subject reference
                fhir_service_request["subject"] = Reference(
                    reference=f"Patient/{patient_id}"
                )
                
                # Add code
                fhir_service_request["code"] = CodeableConcept(
                    coding=[{
                        "system": f"{request.scheme}://{request.host}/fhir/CodeSystem/analysis-types",
                        "code": req["type"],
                        "display": ANALYSIS_TYPES[req["type"]]["display"]
                    }],
                    text=ANALYSIS_TYPES[req["type"]]["definition"]
                )
                
                # Add effective datetime if available
                if req.get("datetime"):
                    fhir_service_request["authoredOn"] = req["datetime"]
                
                # Add region information if available
                if req.get("regions"):
                    fhir_service_request["bodySite"] = []
                    for region in req["regions"]:
                        fhir_service_request["bodySite"].append({
                            "text": region
                        })
                
                # Append the entry
                bundle["entry"].append({
                    "resource": fhir_service_request.to_dict()
                })

            parsed_data['fhir'] = bundle
        else:
            parsed_data['fhir'] = {}
       
        # Return the response
        return json_response(parsed_data)

    except Exception as e:
        return error_response("Patient retrieval failed", 500, {"exception": str(e)})


@require_auth
async def get_request(request):
    """Retrieve detailed service request information by ID.

    Gets detailed service request information from the Hipocrate service including
    medical data, diagnosis, and related studies.

    Args:
        request: The incoming HTTP request with 'id' path parameter for service request ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with service request data or error information
    """
    # Extract service request ID from path
    id = request.match_info.get('id')
    if not id:
        return error_response("Service request ID is required")
    logger.info(f"Retrieving service request with ID: {id}")

    try:
        # Create a new HipoClient instance
        client = HipoClientServiceRequest(SERVICE_URL, request)

        # Retrieve and parse the page
        parsed_data = await client.fetch_and_parse(id=id)

        # Return the response
        return json_response(parsed_data)

    except Exception as e:
        return error_response("Service request retrieval failed", 500, {"exception": str(e)})

@require_auth
async def get_fhir_service_request(request):
    """Retrieve service request information by ID.

    Gets service request information from the Hipocrate service and parses
    the medical data into structured format.

    Args:
        request: The incoming HTTP request with 'id' path parameter for service request ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with service request data or error information

    See:
        https://build.fhir.org/servicerequest.html
    """
    # Extract service request ID from path
    id = request.match_info.get('id')
    if not id:
        return error_response("Service request ID is required")
    logger.info(f"Retrieving service request with ID: {id}")

    try:
        # Create a new HipoClient instance with credentials
        client = HipoClientServiceRequest(SERVICE_URL, request)

        # Retrieve and parse the page, then convert to FHIR resource
        fhir_response, error_resp = await client.fetch_repond_fhir(id=id)

        # Check for errors in the response
        if error_resp:
            return error_resp
        
        # Return the response
        return web.json_response(fhir_response)

    except Exception as e:
        return error_response("Service request retrieval failed", 500, {"exception": str(e)})


@require_auth
async def get_study(request):
    """Retrieve imaging study information by ID.

    Gets imaging study information from the Hipocrate service and parses
    the medical data into structured format.

    Args:
        request: The incoming HTTP request with 'id' path parameter for imaging study ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with imaging study data or error information
    """
    # Extract imaging study ID from path
    id = request.match_info.get('id')
    if not id:
        return error_response("Imaging study ID is required")
    logger.info(f"Retrieving imaging study with ID: {id}")

    try:
        # Create a new HipoClient instance
        client = HipoClientImagingStudy(SERVICE_URL, request)

        # Retrieve and parse the page
        parsed_data = await client.fetch_and_parse(id=id)

        # Return the response
        return json_response(parsed_data)

    except Exception as e:
        return error_response("Imaging study retrieval failed", 500, {"exception": str(e)})

@require_auth
async def get_fhir_imaging_study(request):
    """Retrieve an imaging study by ID, following redirect chains.

    Gets an imaging study from the Hipocrate service, following any redirects to
    retrieve the final report data, then parses it into structured format.

    Args:
        request: The incoming HTTP request with 'id' path parameter for study ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with imaging study data or error information
    """
    # Extract imaging study ID from path
    id = request.match_info.get('id')
    if not id:
        return error_response("Imaging study ID is required")
    logger.info(f"Retrieving imaging study with ID: {id}")

    try:
        # Create a new HipoClient instance with credentials
        client = HipoClientImagingStudy(SERVICE_URL, request)

        # Retrieve and parse the page, then convert to FHIR resource
        response = await client.fetch_repond_fhir(id=id)

        # Return the response
        return json_response(response)

    except Exception as e:
        return error_response("Imaging study retrieval failed", 500, {"exception": str(e)})


@require_auth
async def get_report(request):
    """Retrieve diagnostic report by ID.

    Gets diagnostic report information from the Hipocrate service and parses
    the medical data into structured format.

    Args:
        request: The incoming HTTP request with 'id' path parameter for diagnostic report ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with diagnostic report data or error information
    """
    # Extract diagnostic report ID from path
    id = request.match_info.get('id')
    if not id:
        return error_response("Diagnostic report ID is required")
    logger.info(f"Retrieving diagnostic report with ID: {id}")

    try:
        # Create a new HipoClient instance
        client = HipoClientDiagnosticReport(SERVICE_URL, request)

        # Check if debug response is requested
        debug_resp = await debug_response(client, request, id=id)
        if debug_resp:
            return debug_resp

        # Retrieve and parse the page
        parsed_data = await client.fetch_and_parse(id=id)

        # Return the response
        return json_response(parsed_data)

    except Exception as e:
        return error_response("Diagnostic report retrieval failed", 500, {"exception": str(e)})

@require_auth
async def get_fhir_diagnostic_report(request):
    """Retrieve service request information by ID.

    Gets service request information from the Hipocrate service and parses
    the medical data into structured format.

    Args:
        request: The incoming HTTP request with 'id' path parameter for service request ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with service request data or error information
    """
    # Extract diagnostic report ID from path
    id = request.match_info.get('id')
    if not id:
        return error_response("Diagnostic report ID is required")
    logger.info(f"Retrieving diagnostic report with ID: {id}")

    try:
        # Create a new HipoClient instance with credentials
        client = HipoClientDiagnosticReport(SERVICE_URL, request)

        # Retrieve and parse the page, then convert to FHIR resource
        response = await client.fetch_repond_fhir(id=id)

        # Return the response
        return json_response(response)

    except Exception as e:
        return error_response("Diagnostic report retrieval failed", 500, {"exception": str(e)})


@require_auth
async def get_checkout(request):
    """Retrieve checkout (discharge) information by ID.

    Gets checkout/discharge information from the Hipocrate service and parses
    the medical data into structured format.

    Args:
        request: The incoming HTTP request with 'id' path parameter for checkout ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with checkout data or error information
    """
    # Extract checkout ID from path
    id = request.match_info.get('id')
    if not id:
        return error_response("Checkout ID is required")
    logger.info(f"Retrieving checkout with ID: {id}")

    try:
        # Create a new HipoClient instance
        client = HipoClientCheckout(SERVICE_URL, request)

        # Retrieve and parse the page
        parsed_data = await client.fetch_and_parse(id=id)

        # Return the response
        return json_response(parsed_data)

    except Exception as e:
        return error_response("Checkout retrieval failed", 500, {"exception": str(e)})

@require_auth
async def get_fhir_encounter(request):
    """Retrieve encounter information by ID.

    Gets encounter information from the Hipocrate service and parses
    the medical data into structured format.

    Args:
        request: The incoming HTTP request with 'identifier' query parameter for encounter ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with encounter data or error information

    See:
        https://build.fhir.org/encounter.html
    """
    # Extract encounter ID from path
    id = request.match_info.get('id')
    if not id:
        return error_response("Encounter ID is required")
    logger.info(f"Retrieving encounter with ID: {id}")

    try:
        # Create a new HipoClient instance with credentials
        client = HipoClientCheckout(SERVICE_URL, request)

        # Retrieve and parse the page, then convert to FHIR resource
        fhir_response, error_resp = await client.fetch_repond_fhir(id=id)

        # Check for errors in the response
        if error_resp:
            return error_resp
        
        # Return the response
        return web.json_response(fhir_response)

    except Exception as e:
        return error_response("Encounter retrieval failed", 500, {"exception": str(e)})



async def serve_fhir_analysis_types(request):
    """Serve the analysis types terminology.

    Returns a FHIR CodeSystem resource defining the analysis types used in the hospital system.

    Args:
        request: The incoming HTTP request

    Returns:
        JSON response with CodeSystem resource
    """
    logger.info("GET /fhir/CodeSystem/analysis-types endpoint accessed")

    # Build concepts list using for loop
    concepts = []
    for code, details in ANALYSIS_TYPES.items():
        concepts.append({
            "code": code,
            "display": details["display"],
            "definition": details["definition"]
        })

    # Create FHIR CodeSystem using the FHIR class structure
    code_system = {
        "resourceType": "CodeSystem",
        "id": "analysis-types",
        "url": f"{request.scheme}://{request.host}/fhir/CodeSystem/analysis-types",
        "version": "1.0.0",
        "name": "HospitalAnalysisTypes",
        "title": "Hospital Analysis Types",
        "status": "active",
        "experimental": False,
        "date": datetime.now().strftime('%Y-%m-%d'),
        "publisher": "Hospital System",
        "description": "Code system for analysis types used in the hospital",
        "caseSensitive": True,
        "content": "complete",
        "concept": concepts
    }

    return web.json_response(code_system)


async def serve_spec(request):
    """Serve the OpenAPI specification.

    Returns the OpenAPI specification in JSON format for API documentation.

    Args:
        request: The incoming HTTP request

    Returns:
        JSON response with OpenAPI specification
    """
    logger.info("GET /fhir/spec endpoint accessed")

    try:
        with open('spec.json', 'r') as f:
            spec = json.load(f)
        # Update the server URL with the current PORT
        spec["servers"][0]["url"] = f"{request.scheme}://{request.host}"
        return web.json_response(spec)
    except FileNotFoundError:
        return error_response("Specification file not found", 500)
    except json.JSONDecodeError as e:
        return error_response("Error parsing specification file", 500)


async def serve_fhir_metadata(request):
    """Serve the FHIR capability statement.

    Returns the FHIR capability statement as a metadata endpoint.

    Args:
        request: The incoming HTTP request

    Returns:
        JSON response with FHIR capability statement
    """
    logger.info("GET /fhir/Metadata endpoint accessed")

    # Create a basic FHIR CapabilityStatement
    capability_statement = {
        "resourceType": "CapabilityStatement",
        "id": "hipobridge-fhir-capability-statement",
        "url": f"{request.scheme}://{request.host}/fhir/Metadata",
        "version": "1.0.0",
        "name": "HipoBridgeFHIRCapabilityStatement",
        "title": "HipoBridge FHIR Capability Statement",
        "status": "active",
        "experimental": False,
        "date": datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        "publisher": "HipoBridge",
        "description": "This is the FHIR capability statement for the HipoBridge FHIR API",
        "kind": "instance",
        "software": {
            "name": "HipoBridge",
            "version": "1.0.0"
        },
        "fhirVersion": "4.0.1",
        "format": ["application/fhir+json", "application/json"],
        "rest": [
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
    }

    return web.json_response(capability_statement)




async def serve_md2html(request):
    """Convert markdown text to HTML.

    Takes markdown text and converts it to basic HTML.

    Args:
        request: The incoming HTTP request with JSON body containing 'text' field

    Returns:
        JSON response with HTML content
    """
    logger.info("POST /fhir/md2html endpoint accessed")

    try:
        # Get markdown text from request body
        data = await request.json()
        markdown_text = data.get('text', '')

        html_content = markdown_to_html(markdown_text)

        return web.json_response({
            "status": "success",
            "html": html_content
        })
    except json.JSONDecodeError:
        return error_response("Invalid JSON data")
    except Exception as e:
        return error_response("Markdown conversion failed", 500, {"exception": str(e)})



@require_auth
async def serve_validate_cnp(request):
    """Validate a Romanian CNP (Personal Numerical Code).

    Validates a Romanian CNP using the internal validation algorithm and returns parsed data.

    Args:
        request: The incoming HTTP request with 'id' query parameter for CNP

    Returns:
        JSON response with validation result and parsed data
    """
    logger.info("GET /fhir/ValueSet/cnp endpoint accessed")

    # Get CNP from query string
    cnp = request.query.get('id')

    if not cnp:
        return error_response("CNP is required")

    logger.info(f"Validating CNP: {cnp}")

    # Parse CNP to get detailed information
    parsed_data = parse_cnp(cnp)

    response_data = {
        "status": "success",
        "cnp": cnp,
        "valid": parsed_data.get("valid", False)
    }

    # Add parsed data if valid
    if parsed_data.get("valid"):
        response_data.update({
            "gender": parsed_data.get("gender"),
            "birth_date": parsed_data.get("birth_date"),
            "county_code": parsed_data.get("county_code"),
            "county_name": parsed_data.get("county_name"),
            "serial": parsed_data.get("serial"),
            "control_digit": parsed_data.get("control_digit")
        })

    return web.json_response(response_data)



@require_auth
async def serve_web_page(request):
    """Handle requests to the root endpoint.

    Returns a web page with a CNP input form and analysis functionality.
    Requires basic authentication.

    Args:
        request: The incoming HTTP request

    Returns:
        HTML response with the web interface or 401 if not authenticated
    """
    logger.info("Root endpoint accessed")

    # Get credentials from request (added by decorator)
    username, password = request.auth_credentials

    # Try to login with provided credentials
    client = HipoClient(SERVICE_URL, request)
    session, login_success = await client.get_authenticated_session(username, password)

    if not login_success:
        return web.Response(status=401, headers={'WWW-Authenticate': 'Basic realm="HipoBridge"'})

    # Set cookie with 30-minute expiration
    response = web.StreamResponse()
    response.set_cookie('auth_user', username, max_age=1800, httponly=True)

    # Serve the external HTML file
    with open('static/main.html', 'r') as f:
        html_content = f.read()

    response.content_type = 'text/html'
    await response.prepare(request)
    await response.write(html_content.encode('utf-8'))
    return response



def is_expected_page(soup: BeautifulSoup, expected_title_text: str) -> bool:
    """Check if the parsed HTML content is the expected page by looking for specific text in the title.

    Args:
        soup: BeautifulSoup object of the parsed HTML content
        expected_title_text: Text that should be present in the page title

    Returns:
        True if the page title contains the expected text, False otherwise
    """
    title = soup.find('title')
    return title and expected_title_text in title.get_text()

def error_response(message: str, status_code: int = 400, details: Dict[str, Any] = None) -> web.Response:
    """Create a standardized error response.

    Args:
        message: Error message
        status_code: HTTP status code (default: 400)
        details: Additional error details

    Returns:
        Standardized JSON error response
    """
    if status_code >= 500:
        logger.error(f"{message}")
    else:
        logger.warning(f"{message}")
    # Build response data
    response_data = {
        "status": "error",
        "message": message
    }
    # Include additional details if provided
    if details:
        response_data["details"] = details
    # Return JSON response with appropriate status code
    return web.json_response(response_data, status=status_code)


def json_response(data: Dict[str, Any]) -> web.Response:
    """Create a JSON response with appropriate status code based on data status.

    Args:
        data: Response data dictionary with 'status' field

    Returns:
        JSON response with 200 for success, 404 for error
    """
    status = 200 if data.get("status") == "success" else 404
    return web.json_response(data, status=status)


async def debug_response(client, request, **kwargs) -> web.Response:
    """Handle debug page responses when debug parameter is present.

    Args:
        client: HipoClient instance
        request: The incoming HTTP request
        **kwargs: Arguments to pass to debug_page method

    Returns:
        HTML response with raw page content if debug=page parameter is present,
        None otherwise
    """
    if request.query.get('debug') == 'page':
        result = await client.debug_page(**kwargs)
        return web.Response(body=result, content_type="text/html")
    return None


def load_config():
    """Load configuration from hipp.cfg and local.cfg (if exists).

    Returns:
        dict: Configuration dictionary with merged settings
    """
    config = configparser.ConfigParser()

    # Read default config
    config.read_dict(DEFAULT_CONFIG)

    # Load main config file
    if os.path.exists('hipp.cfg'):
        logger.info("Loading hipp.cfg configuration")
        config.read('hipp.cfg')
    else:
        logger.info("hipp.cfg not found, using default configuration")

    # Load local config if exists (will override hipp.cfg)
    if os.path.exists('local.cfg'):
        logger.info("Loading local.cfg configuration (overrides hipp.cfg)")
        config.read('local.cfg')

    return config

async def on_startup(app):
    """Handle application startup.

    Args:
        app: The web application
    """
    logger.info("Application startup")

async def on_cleanup(app):
    """Handle application cleanup.

    Closes all user HTTP sessions.

    Args:
        app: The web application
    """
    logger.info("Application cleanup")
    await user_session_manager.close_all_sessions()

async def auth_middleware(app, handler):
    """Authentication middleware that skips static files.
    
    Args:
        app: The web application
        handler: The request handler

    Returns:
        Middleware handler
    """
    async def middleware_handler(request):
        # Skip authentication for static files
        if request.path.startswith('/static/'):
            return await handler(request)
        # Apply authentication for other requests
        return await handler(request)
    # Return the middleware handler
    return middleware_handler

async def init_app():
    """Initialize the web application.

    Sets up routes and application lifecycle handlers.

    Returns:
        Configured web application
    """
    logger.info("Initializing web application")

    app = web.Application(middlewares=[auth_middleware])
    app.router.add_get('/', serve_web_page)
    # API endpoints
    app.router.add_get('/api/patient', search_patient)
    app.router.add_get('/api/patient/{id}', get_patient)
    app.router.add_get('/api/request', search_request)
    app.router.add_get('/api/request/{id}', get_request)
    app.router.add_get('/api/study/{id}', get_study)
    app.router.add_get('/api/report/{id}', get_report)
    app.router.add_get('/api/checkout/{id}', get_checkout)
    # FHIR-compatible endpoints
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

    # Setup startup and cleanup
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # Return the configured app
    return app

# Load configuration
config = load_config()

# Configuration values
SERVICE_URL = config.get('hipocrate', 'service_url')
PORT = config.getint('server', 'port')
HOST = config.get('server', 'host')

# Run the application
if __name__ == "__main__":
    logger.info(f"Starting HipoBridge server on {HOST}:{PORT}")
    app = init_app()
    web.run_app(app, host=HOST, port=PORT)
