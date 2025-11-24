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

from hipo import HipoClient, HipoClientCheckout, HipoClientServiceRequest
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


# Analysis types dictionary for reuse across functions
ANALYSIS_TYPES = {
    "radio": {
        "display": "Radiology",
        "definition": "Radiology"
    },
    "ct": {
        "display": "CT Scan",
        "definition": "Computed Tomography"
    },
    "irm": {
        "display": "MRI",
        "definition": "Magnetic Resonance Imaging"
    },
    "eco": {
        "display": "Ultrasound",
        "definition": "Echography"
    },
    "lab": {
        "display": "Laboratory",
        "definition": "Laboratory tests"
    },
    "lac": {
        "display": "Angiography and Cardiac Catheterization",
        "definition": "Angiography and Cardiac Catheterization"
    },
    "lii": {
        "display": "Interventional Radiology",
        "definition": "Interventional Radiology"
    },
    "rads": {
        "display": "Fluoroscopy and CEUS",
        "definition": "Fluoroscopy and Contrast-Enhanced Ultrasound"
    },
    "apa": {
        "display": "Anatomopathology",
        "definition": "Anatomopathology"
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

    # Create a new HipoClient instance with credentials
    client = HipoClient(SERVICE_URL, request)

    try:
        # Make request to the patient endpoint
        request_url = f"/Pacient/edit.asp?id={id}"

        # Retrieve the page
        response_text, success, error_response = await client.get_page(request_url)

        # Check for errors in the response
        if not success:
            return error_response

        # Get patient details
        patient_data = parse_patient_data(response_text)
        if patient_data and patient_data.get("patient_id") and not patient_data.get("error"):
            fhir_patient = create_fhir_patient(patient_data, request)
            return web.json_response(fhir_patient)
        else:
            # Remove the cached response if patient not found
            client.cache_remove(request_url)
            # Return specific error if patient not found
            if patient_data and 'error' in patient_data:
                return create_error_response(patient_data['error'], 404)
            # Return an error if we couldn't read patient data
            return create_error_response("Unable to read patient data", 500)

    except Exception as e:
        return create_error_response("Patient retrieval failed", 500, {"exception": str(e)})

@require_auth
async def search_fhir_patient(request):
    """Search for patients by name or other criteria.

    Performs a patient search on the Hipocrate service using the provided search term.
    Can return either a single patient result or multiple patient results.
    If the search term ends with *, it's treated as a partial CNP search.

    Args:
        request: The incoming HTTP request with 'q' query parameter for search term
                 and basic auth credentials for authentication

    Returns:
        JSON response with search results or error information
    """
    # Get search parameter from query string
    search_term = request.query.get('q', '')
    if not search_term:
        return create_error_response("Search term is required")
    logger.info(f"Searching for patients with term: {search_term}")

    # Create a new HipoClient instance with credentials
    client = HipoClient(SERVICE_URL, request)

    try:
        # Determine search type based on input
        search_type = "name"  # default

        # Check if search term is numeric
        if search_term.isdigit():
            # If it's 13 digits, validate as CNP
            if len(search_term) == 13:
                if validate_cnp(search_term):
                    search_type = "cnp"
                    logger.info(f"Performing CNP search for: {search_term}")
                else:
                    # Not a valid CNP, treat as patient code
                    search_type = "code"
                    logger.info(f"Performing patient code search for: {search_term}")
            else:
                # Numeric but not 13 digits, treat as patient code
                search_type = "code"
                logger.info(f"Performing patient code search for: {search_term}")
        else:
            # Check if search term ends with *, treat as partial CNP
            if search_term.endswith('*'):
                # Validate that the part before * is all digits
                prefix = search_term[:-1]
                if prefix.isdigit() and len(prefix) < 13:
                    search_type = "partial_cnp"
                    logger.info(f"Performing partial CNP search for: {search_term}")
                else:
                    # Not a valid partial CNP, treat as name search
                    search_type = "name"
                    logger.info(f"Searching for patients by name: {search_term}")
            else:
                # Not numeric, treat as name search
                search_type = "name"
                logger.info(f"Searching for patients by name: {search_term}")

        # Prepare full search data as captured in the POST request
        search_data = {
            "hdnSearchType": "1",
            "pageNo": "1",
            "strDescription": search_term if search_type in ["name", "code", "cnp", "partial_cnp"] else "",
            "strLastName": "",
            "strFirstName": "",
            "strCodePres": "",
            "strCNP": "",
            "strSDate": "",
            "strEDate": "",
            "strProfessionID": "",
            "strSex": "",
            "strReference": "",
            "selSection": "0",
            "selDoctor": "",
            "intDiagnosisP": "",
            "DiagnosisP": "",
            "intDiagnosisPDRG": "",
            "DiagnosisPDRG": "",
            "searchWhat": "PA",
            "strShowLastFile": "1",
            "strCheckedIn": "-1",
            "strCODQR": "",
            "btnCODQR": "IMPORTA COD QR",
            "btnCODQRClear": "STERGE COD QR",
            "hdnQRSave": "",
            "IdQR": ""
        }

        # Make search request to the patient search page
        request_url = f"/files/search.asp?what=PA"

        # Post the request
        response_text, success, error_response = await client.post_form(request_url, search_data)

        # Check for errors in the response
        if not success:
            return error_response


        ## Try to parse as single patient page first
        patient_data = parse_patient_data(response_text)
        if patient_data and patient_data.get("patient_id") and not patient_data.get("error"):
            fhir_patient = create_fhir_patient(patient_data, request)
            return web.json_response(fhir_patient)

        # Try to parse as multiple patients page
        multiple_patients_data = parse_multiple_patients_data(response_text)
        if multiple_patients_data and len(multiple_patients_data) > 0:
            # Convert multiple patients to FHIR Bundle
            bundle = {
                "resourceType": "Bundle",
                "type": "searchset",
                "total": len(multiple_patients_data),
                "entry": []
            }
            for patient_id, patient_name in multiple_patients_data.items():
                # Split patient name into family and given names
                name_parts = patient_name.split()
                family_name = name_parts[0] if len(name_parts) > 0 else ""
                given_names = name_parts[1:] if len(name_parts) > 1 else []
                # Create FHIR Patient resource
                fhir_patient = {
                    "resourceType": "Patient",
                    "id": patient_id,
                    "name": [
                        {
                            "use": "official",
                            "family": family_name,
                            "given": given_names
                        }
                    ]
                }
                # Add entry to bundle
                bundle["entry"].append({
                    "resource": fhir_patient
                })
            return web.json_response(bundle)

        # Check if we're on a "no results" page
        # TODO This is not working
        if "nu a fost gasit" in response_text.lower() or "no results" in response_text.lower():
            # Return empty FHIR Bundle
            bundle = {
                "resourceType": "Bundle",
                "type": "searchset",
                "total": 0,
                "entry": []
            }
            return web.json_response(bundle)

        # Log a snippet of the response for debugging
        return create_error_response(
            "Unable to parse patient search results",
            500,
            {"text": response_text[:300] + "..."}
        )

    except Exception as e:
        return create_error_response("Patient search failed", 500, {"exception": str(e)})

def parse_patient_data(html_content: str) -> Dict[str, Any]:
    """Parse HTML content for a single patient page and extract patient data.

    Extracts patient name, CNP, id, and associated encounter/admission/discharge IDs
    from a single patient page HTML content.

    Args:
        html_content: HTML content of the single patient page

    Returns:
        Dictionary containing parsed patient data, or empty dict if not a patient page
        Returns {"error": "Invalid patient id"} if patient name is empty
    """
    # Initialize empty patient data dictionary
    patient_data = {}

    # Inner function to extract data from input elements
    def get_data_from(data_key: str, input_id: str) -> None:
        input_element = soup.find('input', id=input_id)
        if input_element:
            patient_data[data_key] = input_element.get('value', '').strip()

    try:
        # Parse HTML content with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

        # Check if this is a single patient page by looking for 'Date pasaportale' in title
        if not is_expected_page(soup, 'Date pasaportale'):
            # Log snnippet of response for debugging
            return create_error_response("Backend returned an unexpected page", 500, {"text": html_content[:200] + "..."})

        # Check if there is patient data on page by getting the name from the div with id "div_navbar"
        navbar_div = soup.find('div', id='div_navbar')
        if not navbar_div:
            return create_error_response("Invalid patient id", 404)
        patient_name_from_navbar = navbar_div.get_text().strip()
        if not patient_name_from_navbar:
            return create_error_response("Patient name from navbar is empty, invalid patient id", 404)

        # Patient name
        patient_data["patient_name"] = patient_name_from_navbar

        # Extract patient name from input elements
        get_data_from("family_name", "strNume")
        get_data_from("given_name", "strPrenume")
        if patient_data.get("family_name") and patient_data.get("given_name"):
            patient_data["patient_name"] = f"{patient_data['family_name']} {patient_data['given_name']}".strip()

        # Extract patient CNP from input element with id "strCNP"
        get_data_from("patient_cnp", "strCNP")

        # Extract patient id from hidden input with id "hdnCodeID"
        get_data_from("patient_id", "hdnCodeID")

        # Extract CID
        get_data_from("cid", "strCID")

        # Extract phone
        get_data_from("phone", "strTelefon")

        # Extract email
        get_data_from("email", "strEmail")

        # Extract weight
        get_data_from("weight", "strGreutate")

        # Extract height
        get_data_from("height", "strInaltime")

        # Extract MCP
        get_data_from("mcp", "strmcp")

        # Extract address from SELECT with id strDomLegal_LocId
        address_select = soup.find('select', id='strDomLegal_LocId')
        if address_select:
            selected_option = address_select.find('option', selected=True)
            if selected_option:
                patient_data["address"] = selected_option.get_text().strip()

        # Derive sex and birth date from CNP if available
        if patient_data.get("patient_cnp"):
            parsed_cnp = parse_cnp(patient_data["patient_cnp"])
            if parsed_cnp.get("valid"):
                patient_data["sex"] = parsed_cnp.get("gender", "unknown")
                patient_data["birth_date"] = parsed_cnp.get("birth_date", "")

        # If we couldn't derive birth date from CNP, try to get it from strDataNastere input
        if not patient_data.get("birth_date"):
            birth_date_input = soup.find('input', id='strDataNastere', type='text')
            if birth_date_input:
                birth_date_value = birth_date_input.get('value', '').strip()
                # Convert DD/MM/YYYY format to YYYY-MM-DD
                if birth_date_value and re.match(r'\d{2}/\d{2}/\d{4}', birth_date_value):
                    try:
                        day, month, year = birth_date_value.split('/')
                        patient_data["birth_date"] = f"{year}-{month}-{day}"
                    except Exception:
                        pass  # Keep birth_date empty if parsing fails

        # Extract encounters / presentations
        encounter_ids = extract_ids_from_links(soup, r'../files/presentation\.asp\?id=(\d+)')
        if encounter_ids:
            patient_data["encounters"] = encounter_ids

        # Extract admissions / checkins
        admission_ids = extract_ids_from_links(soup, r'../files/checkin\.asp\?id=(\d+)')
        if admission_ids:
            patient_data["admissions"] = admission_ids

        # Extract discharges / checkouts
        discharge_ids = extract_ids_from_links(soup, r'../files/checkout\.asp\?id=(\d+)')
        if discharge_ids:
            patient_data["discharges"] = discharge_ids

        # Return the extracted patient data
        return patient_data
    except Exception as e:
        logger.error(f"Error parsing patient data: {e}")
        return {}

def parse_multiple_patients_data(html_content: str) -> Dict[str, Any]:
    """Parse HTML content for multiple patient search results and extract patient data.

    Extracts patient names, CNP, and ids from search results page with multiple patients.

    Args:
        html_content: HTML content of the search results page

    Returns:
        List of dictionaries containing patient data (name, ID only)
    """
    # Initialize empty list for patients
    patients = {}

    try:
        # Parse HTML content with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

        # Check if this is a search results page by looking for 'Fisier' in title
        if not is_expected_page(soup, 'Fisier'):
            # Log snippet of response for debugging
            #logger.debug(f"Response text snippet: {html_content[:200]}...")
            # Return empty list if not expected page
            return patients

        # Find all links with the pattern javascript:Edit('patient_id')
        pattern = r"javascript:Edit\('([^']+)'\);"
        for link in soup.find_all('a', href=re.compile(pattern)):
            # Extract patient id from href
            patient_id = extract_id_from_link(link, pattern)
            if not patient_id:
                continue

            # Extract patient name from the link text
            patient_name = link.get_text().strip().upper()
            if patient_name == patient_id:
                # If name is same as id, skip this entry (the data is duplicated in Hipocrate)
                continue

            # Add patient data to list
            patients[patient_id] = patient_name
        # Return the list of patients
        return patients

    except Exception as e:
        logger.error(f"Error parsing multiple patients data: {e}")
        return patients

def create_fhir_patient(patient_data: Dict[str, Any], request) -> Dict[str, Any]:
    """Convert patient data to FHIR Patient resource format.

    Args:
        patient_data: Patient data from parse_patient_data
        request: The HTTP request object to get the host

    Returns:
        FHIR Patient resource
    """
    # Use already extracted family name and given name if available
    family_name = patient_data.get("family_name", "")
    given_names = [patient_data.get("given_name", "")] if patient_data.get("given_name") else []

    # Fallback to parsing from full name if family/given names are not available
    if not family_name and not given_names:
        name_parts = patient_data.get("patient_name", "").split()
        family_name = name_parts[0] if len(name_parts) > 0 else ""
        given_names = name_parts[1:] if len(name_parts) > 1 else []

    # Use already extracted gender and birth date if available
    gender = patient_data.get("sex", "unknown")
    birth_date = patient_data.get("birth_date", "")

    # Create FHIR Patient resource using the FHIR class
    fhir_patient = FHIRPatient(
        id=patient_data.get("patient_id", ""),
        active=True,
        gender=gender,
        birthDate=birth_date
    )

    # Add name
    name = {
        "use": "official",
        "family": family_name,
        "given": given_names
    }
    fhir_patient["name"] = [name]

    # Add telecom information if available
    telecom = []
    if patient_data.get("phone", None):
        telecom.append({
            "system": "phone",
            "value": patient_data["phone"]
        })

    if patient_data.get("email", None):
        telecom.append({
            "system": "email",
            "value": patient_data["email"]
        })

    if telecom:
        fhir_patient["telecom"] = telecom

    # Add address information if available
    address = []
    if patient_data.get("address", None):
        address.append({
            "text": patient_data["address"]
        })

    if address:
        fhir_patient["address"] = address

    # Add extensions for additional patient data
    extensions = []

    # Add weight if available
    if patient_data.get("weight", None):
        extensions.append({
            "url": "http://hl7.org/fhir/us/vitals/StructureDefinition/body-weight",
            "valueString": patient_data["weight"]
        })

    # Add height if available
    if patient_data.get("height", None):
        extensions.append({
            "url": "http://hl7.org/fhir/us/vitals/StructureDefinition/height",
            "valueString": patient_data["height"]
        })

    # Add extensions for encounter/admission/discharge IDs
    if "encounters" in patient_data:
        extensions.append({
            "url": f"{request.scheme}://{request.host}/fhir/StructureDefinition/encounter-ids",
            "valueString": ",".join(patient_data["encounters"])
        })
    if "admissions" in patient_data:
        extensions.append({
            "url": f"{request.scheme}://{request.host}/fhir/StructureDefinition/admission-ids",
            "valueString": ",".join(patient_data["admissions"])
        })
    if "discharges" in patient_data:
        extensions.append({
            "url": f"{request.scheme}://{request.host}/fhir/StructureDefinition/discharge-ids",
            "valueString": ",".join(patient_data["discharges"])
        })

    if extensions:
        fhir_patient["extension"] = extensions

    # Add identifiers
    identifiers = []

    # Add CNP as identifier if available
    if patient_data.get("patient_cnp", None):
        identifiers.append({
            "use": "official",
            "system": f"{request.scheme}://{request.host}/fhir/NamingSystem/patient-cnp",
            "value": patient_data["patient_cnp"]
        })

    # Add CID if available
    if patient_data.get("cid", None):
        identifiers.append({
            "system": f"{request.scheme}://{request.host}/fhir/NamingSystem/patient-cid",
            "value": patient_data["cid"]
        })

    # Add MCP if available
    if patient_data.get("mcp", None):
        identifiers.append({
            "system": f"{request.scheme}://{request.host}/fhir/NamingSystem/patient-mcp",
            "value": patient_data["mcp"]
        })

    if identifiers:
        fhir_patient["identifier"] = identifiers

    # Return the FHIR Patient resource as dict
    return fhir_patient.to_dict()


@require_auth
async def get_fhir_diagnostic_report(request):
    """Retrieve a diagnostic report by ID, following redirect chains.

    Gets a diagnostic report from the Hipocrate service, following any redirects to
    retrieve the final report data, then parses it into structured format.

    Args:
        request: The incoming HTTP request with 'id' path parameter for report ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with diagnostic report data or error information
    """
    # Extract report ID from path
    id = request.match_info.get('id')
    if not id:
        return create_error_response("Report ID is required")
    logger.info(f"Retrieving report with ID: {id}")

    # Create a new HipoClient instance with credentials
    client = HipoClient(SERVICE_URL, request)

    try:
        # The report endpoint
        request_url = f"/analyse/Reports/analyseFile.asp?id={id}"

        # Retrieve the page
        response_text, success, error_response = await client.get_page(request_url)

        # Check for errors in the response
        if not success:
            return error_response

        # Return DiagnosticReport
        report_data = parse_report_data(response_text)
        report_data['report_id'] = id
        print(report_data)
        fhir_response = create_fhir_diagnostic_report(report_data, request)
        return web.json_response(fhir_response)

    except Exception as e:
        return create_error_response("Report retrieval failed", 500, {"exception": str(e)})

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
    # Extract study ID from path
    id = request.match_info.get('id')
    if not id:
        return create_error_response("Study ID is required")
    logger.info(f"Retrieving study with ID: {id}")

    # Create a new HipoClient instance with credentials
    client = HipoClient(SERVICE_URL, request)

    try:
        # The study endpoint
        request_url = f"/analyse/Reports/analyseFile.asp?id={id}"

        # Retrieve the page
        response_text, success, error_response = await client.get_page(request_url)

        # Check for errors in the response
        if not success:
            return error_response

        # Return ImagingStudy
        report_data = parse_report_data(response_text)
        report_data['report_id'] = id
        fhir_response = create_fhir_imaging_study(report_data, request)
        return web.json_response(fhir_response)

    except Exception as e:
        return create_error_response("Imaging study retrieval failed", 500, {"exception": str(e)})

def parse_report_data(html_content: str) -> Dict[str, Any]:
    """Parse HTML report content and extract structured data.

    Extracts patient information, examination details, and report results
    from HTML report content.

    Args:
        html_content: HTML content of the report

    Returns:
        Dictionary containing parsed report data
    """
    # Initialize report data dictionary
    report_data = {
        "patient_name": "",
        "age": "",
        "gender": "",
        "patient_cnp": "",
        "patient_id": "",
        "datetime": "",
        "date": "",
        "time": "",
        "examination": "",
        "reports": [],
        "performer": ""
    }

    try:
        # Parse HTML content with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

        # Extract text content for pattern matching
        text_content = soup.get_text()

        # Extract patient name
        name_match = re.search(r'(?:Nume:|PACIENT:)\s*([^\n\r<>&]+?)(?:\s+VARSTA:|\s+SEX:|\s+C\.N\.P:|\s+COD\s+PACIENT:)', text_content, re.IGNORECASE)
        if name_match:
            report_data["patient_name"] = re.sub(r'\s+', ' ', name_match.group(1).strip())
        else:
            # Fallback pattern if the above doesn't match
            name_match = re.search(r'(?:Nume:|PACIENT:)\s*([^\n\r<>&]+)', text_content, re.IGNORECASE)
            if name_match:
                report_data["patient_name"] = re.sub(r'\s+', ' ', name_match.group(1).strip())

        # Extract age
        age_match = re.search(r'Varsta:\s*([^\n\r<>&]+)', text_content, re.IGNORECASE)
        if age_match:
            report_data["age"] = re.sub(r'\s+', ' ', age_match.group(1).strip())

        # Extract gender
        gender_match = re.search(r'Sex:\s*([^\n\r<>&]+)', text_content, re.IGNORECASE)
        if gender_match:
            report_data["gender"] = re.sub(r'\s+', ' ', gender_match.group(1).strip())

        # Extract patient CNP
        cnp_match = re.search(r'C\.N\.P:\s*([^\n\r<>&]+)', text_content, re.IGNORECASE)
        if cnp_match:
            report_data["patient_cnp"] = re.sub(r'\s+', ' ', cnp_match.group(1).strip())

        # Extract patient code
        code_match = re.search(r'Cod pacient:\s*([^\n\r<>&]+)', text_content, re.IGNORECASE)
        if code_match:
            report_data["patient_id"] = re.sub(r'\s+', ' ', code_match.group(1).strip())

        # Extract date and time
        datetime_match = re.search(r'(?:Data si ora recoltarii:|Data investigatiei:)\s*([^\n\r<>&]+)', text_content, re.IGNORECASE)
        dt = None  # Initialize dt variable
        if datetime_match:
            datetime_str = re.sub(r'\s+', ' ', datetime_match.group(1).strip())
            # Try to parse date and time
            try:
                # Handle common date formats
                if re.match(r'\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}', datetime_str):
                    dt = datetime.strptime(datetime_str, '%d/%m/%Y %H:%M:%S')
                elif re.match(r'\d{2}/\d{2}/\d{4}', datetime_str):
                    dt = datetime.strptime(datetime_str, '%d/%m/%Y')
            except ValueError:
                # If parsing fails, leave date/time fields empty
                pass
        report_data["datetime"] = dt

        # Extract performer (Efectuata de catre:)
        performer_match = re.search(r'(?:Efectuata de catre:)\s*([^\n\r<>&]+)', text_content, re.IGNORECASE)
        if performer_match:
            report_data["performer"] = re.sub(r'\s+', ' ', performer_match.group(1).strip())

        # Extract fields using the helper function
        report_data["examination"] = extract_text_after_label(soup, r'EXAMINARE EFECTUATA:', 'td')

        # Extract modality from examination text
        examination_text = report_data["examination"].lower() if report_data["examination"] else ""
        modality_mapping = {
            'radiografia': 'CR',    # Computed Radiography
            'ultrasonografia': 'US',    # Ultrasound
            'tomografia': 'CT',    # Computed Tomography
            'rezonanta': 'MR',    # Magnetic Resonance
            'angiografia': 'XA',    # X-Ray Angiography
            'cisto': 'RF'     # Radio Fluoroscopy
        }

        # Check if any modality code is in the examination text
        for key, modality in modality_mapping.items():
            if key in examination_text:
                report_data["modality"] = modality
                break

        report_data["referral_reason"] = extract_text_after_label(soup, r'DIAGNOSTIC DE TRIMITERE:', 'td')
        report_data["presumptive_diagnosis"] = extract_text_after_label(soup, r'DG\.PREZUMTIV:', 'td')
        report_data["special_indications"] = extract_text_after_label(soup, r'INDICATII SPECIALE:', 'td')
        report_data["referring_physician"] = extract_text_after_label(soup, r'TRIMIS DE:\s*MEDIC', 'td', stop_at=r'SECTIA')

        # Parse referral code and reason if we have referral data
        if report_data["referral_reason"]:
            # Split into code and text - first part numeric is the code, rest is the reason
            parts = report_data["referral_reason"].split(' ', 1)
            if parts:
                # Check if first part is numeric (the code)
                if parts[0].isdigit():
                    report_data["referral_code"] = parts[0]
                    report_data["referral_reason"] = parts[1].strip() if len(parts) > 1 else ""

        # Extract multiple reports: find all elements with text starting with "REZULTAT:"
        for result_element in soup.find_all(string=re.compile(r'^REZULTAT:', re.IGNORECASE)):
            try:
                # The investigation name is the text after "REZULTAT:" in the element
                element_text = result_element.get_text()
                investigation_match = re.search(r'REZULTAT:\s*(.*?)(?:\s*$)', element_text, re.IGNORECASE)
                investigation_name = ""
                if investigation_match:
                    investigation_name = investigation_match.group(1).strip()

                # Find the next div sibling which contains the actual result
                result_div = result_element.find_next('div')
                result_content = ""
                if result_div:
                    # Check if the div contains only a single <b> tag as its child
                    div_children = list(result_div.children)
                    # Filter out text nodes that contain only whitespace
                    element_children = [child for child in div_children if hasattr(child, 'name') and child.name]
                    if len(element_children) == 1 and element_children[0].name == 'b':
                        # If the only child is a <b> tag, use its content directly
                        result_content = html_to_markdown(str(element_children[0]))
                    else:
                        # Otherwise, process the entire div
                        result_content = html_to_markdown(str(result_div))

                # Add to reports list
                # Process investigation name to identify study type and region
                study_type, region = identify_study_type_and_region(investigation_name)
                report_data["reports"].append({
                    "investigation": investigation_name,
                    "result": result_content,
                    "type": study_type,
                    "region": region
                })
            except Exception as e:
                logger.error(f"Error parsing individual report: {e}")
                continue

        # Extract interpreter (MEDIC, or Medic validator:)
        # Handle both plain text and HTML formatted interpreter names
        interpreter_patterns = [
            r'(?:MEDIC,|Medic validator:)\s*([^\n\r<>&]+)',
            r'(?:MEDIC,|Medic validator:)\s*<b[^>]*>([^<]+)</b>',
            r'(?:MEDIC,|Medic validator:)[^>]*>\s*([^\n\r<>&]+)'
        ]
        interpreter_name = ""
        for pattern in interpreter_patterns:
            interpreter_match = re.search(pattern, html_content, re.IGNORECASE)
            if interpreter_match:
                interpreter_name = interpreter_match.group(1).strip()
                # Clean up HTML entities and extra whitespace
                interpreter_name = html.unescape(interpreter_name)
                interpreter_name = re.sub(r'\s+', ' ', interpreter_name)
                break
        if interpreter_name:
            report_data["interpreter"] = interpreter_name
        # Return the parsed report data
        return report_data

    except Exception as e:
        logger.error(f"Error parsing report data: {e}")
        return {}

def parse_report(html_content: str) -> Dict[str, Any]:
    """Parse HTML report content and extract structured data from report.html format.

    Extracts patient information, examination details, and report results
    from HTML report content in the specific format shown in report.html.
    This function parses laboratory reports from the Hipocrate system
    to extract structured data about patient observations.

    Args:
        html_content: HTML content of the report

    Returns:
        Dictionary containing parsed report data organized in sections:
        - patient: Patient information (name, id, cnp, gender, age, birth_date)
        - request: Request information (physician, datetime, barcode, admission_id, diagnosis,
                  clinical_comments, lab_comments, justification, icd10)
        - validation: Validation information (validator, datetime)
        - procedures: List of procedures with their results
        Returns empty dict if parsing fails.
    """
    # Initialize result dictionary
    data = HipoData()

    try:
        # Parse HTML content with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

        # Extract patient name from the table with patient data
        data.store("patient", "name", extract_text_after_label(soup, r'Nume:', 'tr', stop_at=r'\['))

        # Extract patient CNP from the table with patient data
        patient_cnp = extract_value_from_input(soup, id="strCNP")
        data.store("patient", "cnp", patient_cnp)
        if patient_cnp:
            parsed_cnp = parse_cnp(patient_cnp)
            data.store("patient", "gender", parsed_cnp.get("gender", ""))
            data.store("patient", "birth_date", parsed_cnp.get("birth_date", ""))
            data.store("patient", "age", parsed_cnp.get("age", ""))

        # Extract patient code from the table with patient data
        patient_ids = extract_ids_from_links(soup, r'/pacient/edit\.asp\?id=(\d+)')
        if patient_ids:
            data.store("patient", "id", patient_ids[0] if isinstance(patient_ids, list) else patient_ids)
        
        # Extract admission ID
        admission_ids = extract_ids_from_links(soup, r'/files/checkin\.asp\?id=(\d+)')
        if admission_ids:
            data.store("request", "admission_id", admission_ids[0] if isinstance(admission_ids, list) else admission_ids)

        # Extract barcode
        data.store("request", "barcode", extract_text_after_label(soup, r'Cerere de investigatii (?!paraclinice)'))

        # Extract physician
        data.store("request", "physician", extract_text_after_label(soup, r'Medic:', 'tr'))

        # Extract the clinical comments
        data.store("request", "diagnosis", extract_text_after_label(soup, r'prezumtiv:', 'tr'))

        # Extract the clinical comments
        data.store("request", "clinical_comments", extract_text_after_label(soup, r'Informatii suplimentare:', 'tr', stop_at=r'Motiv'))

        # Extract the lab comments
        data.store("request", "lab_comments", extract_text_from_element(soup, id="strComments"))

        # Extract the justification
        data.store("request", "justification", extract_text_from_element(soup, id="strJustificare"))

        # Extract ICD10 coded diagnosis
        data.store("request", "icd10", extract_text_after_label(soup, r'Diagnostic:', 'tr'))

        # Extract requester and request date and time
        req = extract_text_after_label(soup, r'Ceruta:', 'tr')
        if req and '-' in req:
            try:
                request_physician, request_datetime = req.split('-', 1)
                data.store("request", "request_physician", request_physician.strip())
                # Try to parse the datetime
                dt = parse_date_time(request_datetime)
                if dt:
                    data.store("request", "request_datetime", dt.isoformat())
                else:
                    # If parsing fails, keep the original string
                    data.store("request", "request_datetime", request_datetime.strip())
            except ValueError:
                # Handle case where split doesn't work as expected
                data.store("request", "request_info", req)

        # Extract performer (validator) from the domain section
        validator = extract_text_after_label(soup, r'Validat de:', 'td', stop_at=r'Data')
        if validator:
            data.store("validation", "validator", validator)

        # Extract validation datetime
        validation_datetime = extract_value_from_input(soup, id="dataefectuarii")
        if validation_datetime:
            # Try to parse the datetime
            dt = parse_date_time(validation_datetime)
            if dt:
                data.store("validation", "datetime", dt.isoformat())
            else:
                # If parsing fails, keep the original string
                data.store("validation", "datetime", validation_datetime)
        
        # For each strAnalyseExec input, find the parent 'td' and extract examination name from first 'b' element
        procedures = []
        for input_elem in soup.find_all('input', {'name': 'strAnalyseExec'}):
            parent_td = input_elem.find_parent('td')
            if parent_td:
                first_b = parent_td.find('b')
                # Find the 'table' parent and then the 'center' sibling
                parent_table = parent_td.find_parent('table')
                container = parent_table.find_next_sibling('center')
                procedure_result = None
                if container:
                    # In 'center' there is another table.
                    # The rows containing 'rezultat' in first 'td' have the result in second 'td'
                    for row in container.find_all('tr'):
                        cells = row.find_all('td')
                        if len(cells) >= 2:
                            if cells[0].get_text(strip=True).lower() == "rezultat":
                                # Filter out text nodes that contain only whitespace
                                subelements = [child for child in cells[1] if hasattr(child, 'name') and child.name]
                                if len(subelements) == 1 and subelements[0].name == 'b':
                                    # If the only child is a <b> tag, use its content directly
                                    procedure_result = html_to_markdown(str(subelements[0]))
                                else:
                                    # Otherwise, process the entire div
                                    procedure_result = html_to_markdown(str(cells[1]))
                # Append the procedure if the data is valid
                if first_b and procedure_result:
                    procedure = {
                        "title": first_b.get_text(strip=True),
                        "result": procedure_result,
                        "type": "",
                        "region": ""
                    }
                    procedures.append(procedure)
        
        if procedures:
            data.store(None, "procedures", procedures)

        # Store urgency flag
        data.store(None, "is_urgent", "~URGENTA~" in html_content)

        # Return the parsed report data
        return data

    except Exception as e:
        logger.error(f"Error parsing report data: {e}")
        return {}

def create_fhir_diagnostic_report(report_data: Dict[str, Any], request) -> Dict[str, Any]:
    # Create enhanced FHIR DiagnosticReport resource
    fhir_report = {
        "resourceType": "DiagnosticReport",
        "id": report_data["report_id"],
        "status": "final",
        "code": {
            "coding": [
                {
                    "system": f"{request.scheme}://{request.host}/fhir/CodeSystem/report-types",
                    "code": "imaging-report",
                    "display": "Imaging Report"
                }
            ],
            "text": report_data.get("examination", "Imaging Report")
        },
        "subject": {
            "reference": f"Patient/{report_data.get('patient_id', '')}"
        },
        "basedOn": {
            "reference": f"ServiceRequest/{report_data.get('report_id')}"
        },
        "imagingStudy": {
            "reference": f"ImagingStudy/{report_data['report_id']}"
        },

    }

    # Add effective date if available
    if report_data.get("datetime"):
        # Ensure datetime is in proper ISO format
        if isinstance(report_data["datetime"], datetime):
            fhir_report["effectiveDateTime"] = report_data["datetime"].isoformat()
        else:
            fhir_report["effectiveDateTime"] = report_data["datetime"]

    # Add performer if available
    if report_data.get("performer"):
        fhir_report["performer"] = [
            {
                "display": report_data["performer"]
            }
        ]

    # Add results interpreter if available
    if report_data.get("interpreter"):
        fhir_report["resultsInterpreter"] = [
            {
                "display": report_data["interpreter"]
            }
        ]

    # Add results if available
    if report_data.get("reports"):
        fhir_report["result"] = [
            {
                "reference": f"Observation/{report_data['report_id']}"
            }
        ]

        # Add full report text from the first report result
        fhir_report["presentedForm"] = []
        for report in report_data["reports"]:
            # Convert HTML to markdown - no need to encode as base64 since it's text
            markdown_content = html_to_markdown(report["result"])
            fhir_report["presentedForm"].append(
                {
                    "contentType": "text/markdown",
                    "data": markdown_content
                }
            )

        # Add the first report's result text to conclusion
        first_report_result = report_data["reports"][0]["result"] if report_data["reports"] else ""
        fhir_report["conclusion"] = html_to_markdown(first_report_result)

    # Add media references placeholder
    fhir_report["media"] = []

    # Add extensions for referer and reason code/text if available
    extensions = []

    # Add referer if available
    if report_data.get("referring_physician"):
        extensions.append({
            "url": f"{request.scheme}://{request.host}/fhir/StructureDefinition/diagnostic-report-referer",
            "valueString": report_data["referring_physician"]
        })

    # Add reason code and text if available
    if report_data.get("referral_code") or report_data.get("referral_reason"):
        reason_extension = {
            "url": f"{request.scheme}://{request.host}/fhir/StructureDefinition/diagnostic-report-reason",
            "extension": []
        }

        if report_data.get("referral_code"):
            reason_extension["extension"].append({
                "url": "code",
                "valueString": report_data["referral_code"]
            })

        if report_data.get("referral_reason"):
            reason_extension["extension"].append({
                "url": "text",
                "valueString": report_data["referral_reason"]
            })

        extensions.append(reason_extension)

    if extensions:
        fhir_report["extension"] = extensions

    # Return the FHIR Patient resource
    return fhir_report

def create_fhir_imaging_study(report_data: Dict[str, Any], request) -> Dict[str, Any]:
    """Convert report data to FHIR ImagingStudy resource format.

    Args:
        report_data: Report data from parse_report_data
        request: The HTTP request object to get the host

    Returns:
        FHIR ImagingStudy resource
    """
    # Create FHIR ImagingStudy resource
    fhir_imaging_study = {
        "resourceType": "ImagingStudy",
        "id": report_data["report_id"],
        "status": "available",
        "subject": {
            "reference": f"Patient/{report_data.get('patient_id', '')}"
        },
        "basedOn": {
            "reference": f"ServiceRequest/{report_data.get('report_id')}"
        },
        "started": report_data["datetime"].isoformat() if report_data.get("datetime") else datetime.now().isoformat(),
        "series": []
    }

    # Add modality if available
    if report_data.get("modality"):
        fhir_imaging_study["modality"] = {
            "system": "http://dicom.nema.org/resources/ontology/DCM",
            "code": report_data["modality"].upper(),
            "display": report_data["modality"].upper()
        }

    # Add patient information if available
    if report_data.get("patient_name"):
        fhir_imaging_study["identifier"] = [{
            "system": f"{request.scheme}://{request.host}/fhir/NamingSystem/patient-name",
            "value": report_data["patient_name"]
        }]

    if report_data.get("patient_cnp"):
        if "identifier" not in fhir_imaging_study:
            fhir_imaging_study["identifier"] = []
        fhir_imaging_study["identifier"].append({
            "system": f"{request.scheme}://{request.host}/fhir/NamingSystem/patient-cnp",
            "value": report_data["patient_cnp"]
        })

    # Add description from examination
    if report_data.get("examination"):
        fhir_imaging_study["description"] = report_data["examination"]

    # Add performer if available
    if report_data.get("performer"):
        fhir_imaging_study["performer"] = [
            {
                "actor": {
                    "display": report_data["performer"]
                }
            }
        ]

    # Add referrer if referring physician is available
    if report_data.get("referring_physician"):
        fhir_imaging_study["referrer"] = {
            "display": report_data["referring_physician"]
        }

    # Add series for each report
    if report_data.get("reports"):
        for i, report in enumerate(report_data["reports"]):
            series = {
                "uid": f"urn:oid:1.2.840.99999999.1.{report_data['report_id']}.{i+1}",
                "number": i+1,
                "modality": {
                    "system": "http://dicom.nema.org/resources/ontology/DCM",
                    "code": "OT",  # Other
                    "display": "Other"
                },
                "description": report.get("investigation", "Imaging Study"),
                "started": report_data["datetime"].isoformat() if report_data.get("datetime") else datetime.now().isoformat(),
                "instance": []
            }
            # Use the study modality for the series if available, otherwise default to OT
            series_modality = report_data.get("modality", "OT")
            series["modality"] = {
                "system": "http://dicom.nema.org/resources/ontology/DCM",
                "code": series_modality.upper(),
                "display": series_modality.upper()
            }
            # Add the instance
            fhir_imaging_study["series"].append(series)

    # Add reason for study if referral information is available
    if report_data.get("referral_reason") or report_data.get("referral_code"):
        reason_text = ""
        if report_data.get("referral_code"):
            reason_text += f"Code: {report_data['referral_code']}"
        if report_data.get("referral_reason"):
            if reason_text:
                reason_text += " - "
            reason_text += report_data["referral_reason"]

        fhir_imaging_study["reason"] = [
            {
                "text": reason_text
            }
        ]

    # Add note if presumptive diagnosis is available
    if report_data.get("presumptive_diagnosis"):
        fhir_imaging_study["note"] = [
            {
                "text": report_data["presumptive_diagnosis"]
            }
        ]

    # Add description if special _indications are available
    if report_data.get("special_indications"):
        fhir_imaging_study["description"] = report_data["presumptive_diagnosis"]

    return fhir_imaging_study

@require_auth
async def get_fhir_observation(request):
    """Retrieve a single observation by ID.

    Gets detailed information for a specific observation from the Hipocrate service.

    Args:
        request: The incoming HTTP request with 'id' path parameter for observation ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with observation data or error information
    """
    # Extract observation ID from path
    id = request.match_info.get('id')
    if not id:
        return create_error_response("Observation ID is required")
    logger.info(f"Retrieving observation with ID: {id}")

    # Create a new HipoClient instance with credentials
    client = HipoClient(SERVICE_URL, request)

    try:
        # The observation endpoint
        #request_url = f"/analyse/Reports/analyseFile_4212-lab.asp?fullpacient=yes&id={id}&section=4212-lab"
        request_url = f"/analyse/labrequest/edit.asp?id={id}"

        # Retrieve the page
        response_text, success, error_response = await client.get_page(request_url)

        # Check for errors in the response
        if not success:
            return error_response

        # Return Observation
        report_data = parse_report(response_text)
        report_data['report_id'] = id
        fhir_response = create_fhir_observation(report_data, request)
        return web.json_response(fhir_response)

    except Exception as e:
        return create_error_response("Observation retrieval failed", 500, {"exception": str(e)})

def create_fhir_observation(report_data: Dict[str, Any], request) -> Dict[str, Any]:
    """Convert report data to FHIR Observation resource format.

    Args:
        report_data: Report data from parse_report_data
        request: The HTTP request object to get the host

    Returns:
        FHIR Observation resource
    """
    # Create FHIR Observation resource
    fhir_observation = {
        "resourceType": "Observation",
        "id": report_data["report_id"],
        "status": "final",
        "code": {
            "coding": [
                {
                    "system": f"{request.scheme}://{request.host}/fhir/CodeSystem/analysis-types",
                    "code": "unknown",
                    "display": "Analysis"
                }
            ],
            "text": report_data.get("examination", "Analysis")
        },
        "subject": {
            "reference": f"Patient/{report_data.get('patient_id', '')}"
        },
        "basedOn": {
            "reference": f"ServiceRequest/{report_data.get('report_id')}"
        },
    }

    # Add effective datetime if available
    if report_data.get("request_datetime"):
        fhir_observation["effectiveDateTime"] = report_data["request_datetime"]
    elif report_data.get("validation_datetime"):
        fhir_observation["effectiveDateTime"] = report_data["validation_datetime"]

    # Add performer if available
    if report_data.get("performer"):
        fhir_observation["performer"] = [
            {
                "display": report_data["performer"]
            }
        ]
    elif report_data.get("validator"):
        fhir_observation["performer"] = [
            {
                "display": report_data["validator"]
            }
        ]

    # Add value/comment if available
    if report_data.get("reports"):
        fhir_observation["note"] = []
        for report in report_data["reports"]:
            fhir_observation["note"].append(
                {
                    "text": report["result"]
                }
            )

    # Add extensions for additional data
    extensions = []

    # Add physician information
    if report_data.get("physician"):
        extensions.append({
            "url": f"{request.scheme}://{request.host}/fhir/StructureDefinition/observation-requester",
            "valueString": report_data["physician"]
        })

    # Add admission ID if available
    if report_data.get("admission_id"):
        extensions.append({
            "url": f"{request.scheme}://{request.host}/fhir/StructureDefinition/observation-encounter",
            "valueString": report_data["admission_id"]
        })

    # Add barcode if available
    if report_data.get("barcode"):
        extensions.append({
            "url": f"{request.scheme}://{request.host}/fhir/StructureDefinition/observation-barcode",
            "valueString": report_data["barcode"]
        })

    # Add clinical comments if available
    if report_data.get("clinical_comments"):
        extensions.append({
            "url": f"{request.scheme}://{request.host}/fhir/StructureDefinition/observation-clinical-comments",
            "valueString": report_data["clinical_comments"]
        })

    # Add lab comments if available
    if report_data.get("lab_comments"):
        extensions.append({
            "url": f"{request.scheme}://{request.host}/fhir/StructureDefinition/observation-lab-comments",
            "valueString": report_data["lab_comments"]
        })

    # Add diagnosis if available
    if report_data.get("diagnosis"):
        extensions.append({
            "url": f"{request.scheme}://{request.host}/fhir/StructureDefinition/observation-diagnosis",
            "valueString": report_data["diagnosis"]
        })

    if extensions:
        fhir_observation["extension"] = extensions

    # Add identifiers
    identifiers = []

    # Add barcode as identifier if available
    if report_data.get("barcode"):
        identifiers.append({
            "system": f"{request.scheme}://{request.host}/fhir/NamingSystem/barcode",
            "value": report_data["barcode"]
        })

    if identifiers:
        fhir_observation["identifier"] = identifiers

    return fhir_observation

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
        parsed_data, error_response = await client.fetch_and_parse(id=id)

        # Check for errors in the response
        if error_response:
            return error_response

        # Return the response
        return web.json_response(parsed_data)

    except Exception as e:
        return create_error_response("Checkout retrieval failed", 500, {"exception": str(e)})

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
        parsed_data, error_response = await client.fetch_and_parse(id=id)

        # Check for errors in the response
        if error_response:
            return error_response

        # Return the response
        return web.json_response(parsed_data)

    except Exception as e:
        return create_error_response("Service request retrieval failed", 500, {"exception": str(e)})

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





def parse_date_time(date_str: str) -> Optional[datetime]:
    """Parse a date string in the format '30 Aug 2025 19:25:00'.

    Args:
        date_str: Date string to parse

    Returns:
        datetime object if parsing successful, None otherwise
    """
    try:
        # Handle common date formats like "30 Aug 2025 19:25:00"
        # Create a mapping for month abbreviations to numbers
        month_mapping = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12,
            'Ian': 1, 'Mai': 5, 'Iun': 6, 'Iul': 7  # Romanian month abbreviations
        }

        # Split the date string into components
        parts = date_str.strip().split()
        if len(parts) != 4:
            return None

        day = int(parts[0])
        month_abbr = parts[1]
        year = int(parts[2])
        time_part = parts[3]

        # Get month number from mapping
        if month_abbr not in month_mapping:
            return None
        month = month_mapping[month_abbr]

        # Parse time
        time_parts = time_part.split(':')
        if len(time_parts) == 2:
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            second = 0
        elif len(time_parts) == 3:
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            second = int(time_parts[2])
        else:
            return None

        # Create datetime object
        return datetime(year, month, day, hour, minute, second)
    except (ValueError, IndexError, TypeError):
        # If parsing fails, return None
        return None

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


def validate_cnp(cnp: str) -> bool:
    """Validate a Romanian CNP (Personal Numerical Code).

    Checks if the provided string is a valid Romanian CNP by verifying:
    - Length (13 digits)
    - Gender digit (1-8)
    - Date components (year, month, day)
    - County code (1-52, excluding 47-50)
    - Control digit using checksum algorithm

    Args:
        cnp: The CNP to validate

    Returns:
        True if CNP is valid, False otherwise
    """
    parsed_data = parse_cnp(cnp)
    return parsed_data.get("valid", False)

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
    session, login_success = await client.get_authenticated_session(client.username, client.password)

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
    # API endpointa
    app.router.add_get('/api/checkout/{id}', get_checkout)
    app.router.add_get('/api/request/{id}', get_request)
    # FHIR-compatible endpoints
    app.router.add_get('/fhir/Patient', search_fhir_patient)
    app.router.add_get('/fhir/Patient/{id}', get_fhir_patient)
    app.router.add_get('/fhir/DiagnosticReport/{id}', get_fhir_diagnostic_report)
    app.router.add_get('/fhir/ImagingStudy/{id}', get_fhir_imaging_study)
    app.router.add_get('/fhir/Encounter/{id}', get_fhir_encounter)
    app.router.add_get('/fhir/Observation', search_fhir_observation)
    app.router.add_get('/fhir/Observation/{id}', get_fhir_observation)
    app.router.add_get('/fhir/ServiceRequest/{id}', get_fhir_service_request)
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
