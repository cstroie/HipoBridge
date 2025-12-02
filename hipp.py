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
from hipo import HipoData, user_session_manager, identify_study_type_and_region

from extractors import extract_id_from_link, extract_ids_from_links, extract_selected_from_dropdown, extract_tabular_data, extract_text_after_label, extract_text_from_element, extract_textarea_after_label, extract_value_from_input
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
    """Retrieve service request information by ID.

    Gets service request information from the Hipocrate service and parses
    the medical data into structured format.

    Args:
        request

    Returns:
        JSON response with service request data or error information
    """
    # Get search parameter from query string
    search_term = request.query.get('q', '')
    if not search_term:
        return create_error_response("Search term is required")
    logger.info(f"Searching for patients with term: {search_term}")

    try:
        # Create a new HipoClient instance with credentials
        client = HipoClientPatientSearch(SERVICE_URL, request)

        # Retrieve and parse the page
        parsed_data = await client.search(search_term)

        # Check for errors in the response
        status = 200 if parsed_data.get("status") == "success" else 404
        
        # Return the response
        return web.json_response(parsed_data, status = status)

    except Exception as e:
        return create_error_response("Patient retrieval failed", 500, {"exception": str(e)})


@require_auth
async def search_fhir_patient(request):
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
    search_term = request.query.get('q', '')
    if not search_term:
        return create_error_response("Search term is required")
    logger.info(f"Searching for patients with term: {search_term}")

    try:
        # Create a new HipoClient instance with credentials
        client = HipoClientPatientSearch(SERVICE_URL, request)

        # Retrieve and parse the page
        parsed_data = await client.search(search_term)

        # Check for errors in the response
        status = 200 if parsed_data.get("status") == "success" else 404

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
        return web.json_response(parsed_data["fhir"], status = status)

    except Exception as e:
        return create_error_response("Patient retrieval failed", 500, {"exception": str(e)})


@require_auth
async def get_patient(request):
    """Retrieve service request information by ID.

    Gets service request information from the Hipocrate service and parses
    the medical data into structured format.

    Args:
        request

    Returns:
        JSON response with service request data or error information
    """
    # Extract service request ID from path
    id = request.match_info.get('id')
    if not id:
        return create_error_response("Service request ID is required")
    logger.info(f"Retrieving service request with ID: {id}")

    try:
        # Create a new HipoClient instance with credentials
        client = HipoClientPatient(SERVICE_URL, request)

        # Retrieve and parse the page
        parsed_data = await client.fetch_and_parse(id=id)

        # Check for errors in the response
        status = 200 if parsed_data.get("status") == "success" else 404
        
        # Return the response
        return web.json_response(parsed_data, status = status)

    except Exception as e:
        return create_error_response("Patient retrieval failed", 500, {"exception": str(e)})

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
        return create_error_response("Patient ID is required")
    logger.info(f"Retrieving patient with ID: {id}")

    try:
        # Create a new HipoClient instance with credentials
        client = HipoClientPatient(SERVICE_URL, request)

        # Retrieve and parse the page, then convert to FHIR resource
        response = await client.fetch_repond_fhir(id=id)

        # Check for errors in the response
        status = 200 if response.get("status") == "success" else 404
        
        # Return the response
        return web.json_response(response["fhir"], status = status)

    except Exception as e:
        return create_error_response("Patient retrieval failed", 500, {"exception": str(e)})



@require_auth
async def search_request(request):
    """Retrieve service requests for patient.

    Gets service request information from the Hipocrate service and parses
    the medical data into structured format.

    Args:
        request

    Returns:
        JSON response with service request data or error information
    """
    # Get search parameter from query string
    patient_id = request.query.get('patient', '')
    if not patient_id:
        return create_error_response("Patient ID is required")
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

        # Check for errors in the response
        status = 200 if parsed_data.get("status") == "success" else 404
        
        # Return the response
        return web.json_response(parsed_data, status = status)

    except Exception as e:
        return create_error_response("Service requests retrieval failed", 500, {"exception": str(e)})



@require_auth
async def get_request(request):
    """Retrieve service request information by ID.

    Gets service request information from the Hipocrate service and parses
    the medical data into structured format.

    Args:
        request

    Returns:
        JSON response with service request data or error information
    """
    # Extract service request ID from path
    id = request.match_info.get('id')
    if not id:
        return create_error_response("Service request ID is required")
    logger.info(f"Retrieving service request with ID: {id}")

    try:
        # Create a new HipoClient instance
        client = HipoClientServiceRequest(SERVICE_URL, request)

        # Retrieve and parse the page
        parsed_data = await client.fetch_and_parse(id=id)

        # Check for errors in the response
        status = 200 if parsed_data.get("status") == "success" else 404
        
        # Return the response
        return web.json_response(parsed_data, status = status)

    except Exception as e:
        return create_error_response("Service request retrieval failed", 500, {"exception": str(e)})

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
        return create_error_response("Service request ID is required")
    logger.info(f"Retrieving service request with ID: {id}")

    try:
        # Create a new HipoClient instance with credentials
        client = HipoClientServiceRequest(SERVICE_URL, request)

        # Retrieve and parse the page, then convert to FHIR resource
        fhir_response, error_response = await client.fetch_repond_fhir(id=id)

        # Check for errors in the response
        if error_response:
            return error_response
        
        # Return the response
        return web.json_response(fhir_response)

    except Exception as e:
        return create_error_response("Service request retrieval failed", 500, {"exception": str(e)})


@require_auth
async def get_study(request):
    """Retrieve imaging study by ID.

    Gets service request information from the Hipocrate service and parses
    the medical data into structured format.

    Args:
        request

    Returns:
        JSON response with service request data or error information
    """
    # Extract service request ID from path
    id = request.match_info.get('id')
    if not id:
        return create_error_response("Imaging study ID is required")
    logger.info(f"Retrieving imaging study with ID: {id}")

    try:
        # Create a new HipoClient instance
        client = HipoClientImagingStudy(SERVICE_URL, request)

        # Retrieve and parse the page
        parsed_data = await client.fetch_and_parse(id=id)

        # Check for errors in the response
        status = 200 if parsed_data.get("status") == "success" else 404
        
        # Return the response
        return web.json_response(parsed_data, status = status)

    except Exception as e:
        return create_error_response("Imaging study retrieval failed", 500, {"exception": str(e)})

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
        return create_error_response("Imaging study ID is required")
    logger.info(f"Retrieving imaging study with ID: {id}")

    try:
        # Create a new HipoClient instance with credentials
        client = HipoClientImagingStudy(SERVICE_URL, request)

        # Retrieve and parse the page, then convert to FHIR resource
        response = await client.fetch_repond_fhir(id=id)

        # Check for errors in the response
        status = 200 if response.get("status") == "success" else 404
        
        # Return the response
        return web.json_response(response.get("fhir", response), status = status)

    except Exception as e:
        return create_error_response("Imaging study retrieval failed", 500, {"exception": str(e)})


@require_auth
async def get_report(request):
    """Retrieve diagnostic report by ID.

    Gets service request information from the Hipocrate service and parses
    the medical data into structured format.

    Args:
        request

    Returns:
        JSON response with service request data or error information
    """
    # Extract service request ID from path
    id = request.match_info.get('id')
    if not id:
        return create_error_response("Diagnostic report ID is required")
    logger.info(f"Retrieving diagnostic report with ID: {id}")

    try:
        # Create a new HipoClient instance
        client = HipoClientDiagnosticReport(SERVICE_URL, request)

        if request.query.get('debug') == 'page':
            result = await client.debug_page(id=id)
            return web.Response(body = result, content_type="text/html")

        # Retrieve and parse the page
        parsed_data = await client.fetch_and_parse(id=id)

        # Check for errors in the response
        status = 200 if parsed_data.get("status") == "success" else 404
        
        # Return the response
        return web.json_response(parsed_data, status = status)

    except Exception as e:
        return create_error_response("Diagnostic report retrieval failed", 500, {"exception": str(e)})

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
        return create_error_response("Diagnostic report ID is required")
    logger.info(f"Retrieving diagnostic report with ID: {id}")

    try:
        # Create a new HipoClient instance with credentials
        client = HipoClientDiagnosticReport(SERVICE_URL, request)

        # Retrieve and parse the page, then convert to FHIR resource
        response = await client.fetch_repond_fhir(id=id)

        # Check for errors in the response
        status = 200 if response.get("status") == "success" else 404
        
        # Return the response
        return web.json_response(response.get("fhir", response), status = status)

    except Exception as e:
        return create_error_response("Diagnostic report retrieval failed", 500, {"exception": str(e)})


@require_auth
async def get_checkout(request):
    """Retrieve checkout information by ID.

    Gets checkout information from the Hipocrate service and parses
    the medical data into structured format.

    Args:
        request

    Returns:
        JSON response with checkout data or error information
    """
    # Extract encounter ID from path
    id = request.match_info.get('id')
    if not id:
        return create_error_response("Checkout ID is required")
    logger.info(f"Retrieving checkout with ID: {id}")

    try:
        # Create a new HipoClient instance
        client = HipoClientCheckout(SERVICE_URL, request)

        # Retrieve and parse the page
        parsed_data = await client.fetch_and_parse(id=id)

        # Check for errors in the response
        status = 200 if parsed_data.get("status") == "success" else 404
        
        # Return the response
        return web.json_response(parsed_data, status = status)

    except Exception as e:
        return create_error_response("Checkout retrieval failed", 500, {"exception": str(e)})

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
        return create_error_response("Encounter ID is required")
    logger.info(f"Retrieving encounter with ID: {id}")

    try:
        # Create a new HipoClient instance with credentials
        client = HipoClientCheckout(SERVICE_URL, request)

        # Retrieve and parse the page, then convert to FHIR resource
        fhir_response, error_response = await client.fetch_repond_fhir(id=id)

        # Check for errors in the response
        if error_response:
            return error_response
        
        # Return the response
        return web.json_response(fhir_response)

    except Exception as e:
        return create_error_response("Encounter retrieval failed", 500, {"exception": str(e)})






@require_auth
async def search_fhir_observation(request):
    """Retrieve list of observations for a patient by ID.

    Gets a list of observations for a specific patient from the Hipocrate service
    without fetching detailed data for each observation.

    Args:
        request: The incoming HTTP request with 'patient' query parameter for patient ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with observations data or error information
    """
    # Extract patient ID from query parameters
    patient_id = request.query.get('patient')
    if not patient_id:
        return create_error_response("Patient ID is required")
    logger.info(f"Retrieving analyses list for patient with ID: {patient_id}")

    # Create a new HipoClient instance with credentials
    client = HipoClient(SERVICE_URL, request)

    # Get optional parameters
    exam_type = request.query.get('type')
    exam_region = request.query.get('region')
    exam_datetime = request.query.get('dt')
    full_data = request.query.get('full', 'no').lower() == 'yes'

    try:
        # The analyses endpoint
        request_url = f"/pacient/analyses.asp?type=PA&pacid={patient_id}"
        # Add full=yes parameter if requested
        if full_data:
            request_url += "&full=yes"

        # Retrieve the page
        response_text, success, error_response = await client.get_page(request_url)

        # Check for errors in the response
        if not success:
            return error_response

        # Parse the analyses data to extract report IDs, types, and patient name
        parsed_data = parse_analyses_data(response_text)

        # Filter analyses by type if specified
        analyses = parsed_data["analyses"]
        if exam_type:
            analyses = [a for a in analyses if a["type"] == exam_type]
            
        # Filter analyses by region if specified
        if exam_region:
            analyses = [a for a in analyses if a.get("region") == exam_region]

        # Filter analyses by datetime if specified
        if exam_datetime:
            # Parse the datetime string to match against analysis datetimes
            try:
                target_dt = datetime.fromisoformat(exam_datetime.replace('Z', '+00:00'))
                # Start with a date range from one day earlier to one day after
                hours_range = 24
                max_attempts = 3

                for attempt in range(max_attempts):
                    start_dt = target_dt - timedelta(hours=hours_range)
                    end_dt = target_dt + timedelta(hours=hours_range)

                    filtered_analyses = []
                    for a in analyses:
                        if "datetime" in a and start_dt <= a["datetime"] <= end_dt:
                            filtered_analyses.append(a)

                    # If we found exactly one observation, return it
                    if len(filtered_analyses) == 1:
                        analyses = filtered_analyses
                        break
                    # If we found multiple observations, reduce the time range and try again
                    elif len(filtered_analyses) > 1 and attempt < max_attempts - 1:
                        hours_range = hours_range / 2
                        continue
                    # If no observations or on final attempt, return what we found
                    else:
                        analyses = filtered_analyses
                        break

            except ValueError:
                logger.warning(f"Invalid datetime format: {exam_datetime}")

        # Create FHIR Bundle of Observation resources (minimal data only)
        bundle = {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": len(analyses),
            "entry": []
        }

        for analysis in analyses:
            fhir_observation = {
                "resourceType": "Observation",
                "id": analysis["analysis_id"],
                "status": "final",
                "code": {
                    "coding": [
                        {
                            "system": f"{request.scheme}://{request.host}/fhir/CodeSystem/analysis-types",
                            "code": analysis["type"],
                            "display": ANALYSIS_TYPES[analysis["type"]]["display"]
                        }
                    ],
                    "text": ANALYSIS_TYPES[analysis["type"]]["definition"]
                },
                "subject": {
                    "reference": f"Patient/{patient_id}"
                },
                "basedOn": {
                    "reference": f"ServiceRequest/{analysis.get('analysis_id')}"
                },
            }

            # Add effective datetime if available
            if analysis.get("datetime"):
                fhir_observation["effectiveDateTime"] = analysis["datetime"].isoformat()

            bundle["entry"].append({
                "resource": fhir_observation
            })

        return web.json_response(bundle)

    except Exception as e:
        return create_error_response("Analyses list retrieval failed", 500, {"exception": str(e)})

def parse_analyses_data(html_content: str) -> Dict[str, Any]:
    """Parse HTML analyses content and extract analysis IDs, analysis types, patient name, and patient id.

    Extracts patient name, patient id, and list of analyses with their types and analysis IDs
    from the analyses HTML page.

    Args:
        html_content: HTML content of the analyses page

    Returns:
        Dictionary containing patient name, patient id, and list of analyses
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')

        # Check if this is the correct page by looking for 'Cereri de Laborator' in title
        if not is_expected_page(soup, 'Cereri de Laborator'):
            logger.warning("Page is not a laboratory requests page")
            return {"patient_name": "", "patient_id": "", "analyses": []}

        # Initialize result
        result = {
            "patient_name": "",
            "patient_id": "",
            "analyses": []
        }

        # Extract patient name and id from the link pattern
        patient_link = soup.find('a', href=re.compile(r'../Pacient/edit\.asp\?id=\d+'))
        if patient_link:
            result["patient_name"] = patient_link.get_text().strip()
            # Extract patient id from href
            href = patient_link.get('href', '')
            code_match = re.search(r'id=(\d+)', href)
            if code_match:
                result["patient_id"] = code_match.group(1)

        # Extract CNP from table (next TD after 'CNP:')
        cnp_cells = soup.find_all('td', string=re.compile(r'CNP:', re.IGNORECASE))
        for cnp_cell in cnp_cells:
            next_td = cnp_cell.find_next('td')
            if next_td:
                cnp_text = next_td.get_text().strip()
                if cnp_text and cnp_text.isdigit() and len(cnp_text) == 13:
                    result["patient_cnp"] = cnp_text
                    break

        # Find all links to analysis
        for link in soup.find_all('a', href=re.compile(r'../analyse/Reports/analyseFile\.asp\?id=\d+')):
            # Extract analysis ID
            analysis_id = extract_id_from_link(link, r'id=(\d+)')
            if not analysis_id:
                continue

            # Find the parent table row
            parent_row = link.find_parent('tr')
            if not parent_row:
                # If no parent row, just add the ID without type
                result["analyses"].append({
                    "analysis_id": analysis_id,
                    "type": "unknown"
                })
                continue

            # Extract information from table cells
            analysis_data = {
                "analysis_id": analysis_id,
                "type": "unknown"
            }

            cells = parent_row.find_all('td')
            if len(cells) >= 8:
                # Cell 0: Checkbox (ignore)
                # Cell 1: Report link (already processed)
                # Cell 2: Barcode (ignore)
                # Cell 3: Checkin code
                checkin_link = cells[3].find('a', href=re.compile(r'/files/checkin\.asp\?id=\d+'))
                if checkin_link:
                    checkin_href = checkin_link.get('href', '')
                    checkin_match = re.search(r'id=(\d+)', checkin_href)
                    if checkin_match:
                        analysis_data["admission"] = checkin_match.group(1)

                # Cell 4: Date
                date_text = cells[4].get_text().strip()
                if date_text:
                    analysis_data["date"] = date_text
                    # Try to parse the date string into a proper datetime object
                    try:
                        # Handle common date formats like "07 Nov 2025 10:29:00"
                        # Create a mapping for Romanian month abbreviations to English ones
                        month_mapping = {
                            'Ian': 'Jan', 'Mai': 'May', 'Iun': 'Jun', 'Iul': 'Jul'
                        }

                        # Replace Romanian month abbreviations with English ones
                        formatted_date = date_text
                        for ro_month, en_month in month_mapping.items():
                            formatted_date = formatted_date.replace(ro_month, en_month)

                        # Parse the datetime using strptime
                        analysis_data["datetime"] = datetime.strptime(formatted_date, '%d %b %Y %H:%M:%S')
                    except Exception as e:
                        logger.debug(f"Could not parse datetime from string '{date_text}': {e}")
                        # Keep the original string if parsing fails

                # Cell 5: Priority
                priority_text = cells[5].get_text().strip()
                if priority_text:
                    analysis_data["priority"] = priority_text

                # Cell 6: Analysis type
                type_text = cells[6].get_text().strip()
                # Look for pattern like 'XXXX-Radio', 'XXXX-lab', etc.
                type_match = re.search(r'\d{4}-(\w+)', type_text)
                if type_match:
                    extracted_type = type_match.group(1).lower()
                    # Check if the extracted type is in our known analysis types
                    if extracted_type in ANALYSIS_TYPES:
                        analysis_data["type"] = extracted_type
                    else:
                        analysis_data["type"] = "other"
                else:
                    analysis_data["type"] = "other"

                # Cell 7: Requesting doctor
                doctor_text = cells[7].get_text().strip()
                if doctor_text:
                    analysis_data["requesting_doctor"] = doctor_text
            # Append the analysis data to the result list
            result["analyses"].append(analysis_data)
        # Return the parsed result
        return result

    except Exception as e:
        logger.error(f"Error parsing analyses data: {e}")
        return {"patient_name": "", "patient_id": "", "analyses": []}





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
        return create_error_response("Specification file not found", 500)
    except json.JSONDecodeError as e:
        return create_error_response("Error parsing specification file", 500)


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
                        "type": "Observation",
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
        return create_error_response("Invalid JSON data")
    except Exception as e:
        return create_error_response("Markdown conversion failed", 500, {"exception": str(e)})



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
        return create_error_response("CNP is required")

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

def create_error_response(message: str, status_code: int = 400, details: Dict[str, Any] = None) -> web.Response:
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
    app.router.add_get('/fhir/ServiceRequest/{id}', get_fhir_service_request)
    app.router.add_get('/fhir/ImagingStudy/{id}', get_fhir_imaging_study)
    app.router.add_get('/fhir/DiagnosticReport/{id}', get_fhir_diagnostic_report)
    app.router.add_get('/fhir/Encounter/{id}', get_fhir_encounter)
    app.router.add_get('/fhir/Observation', search_fhir_observation)
    
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
