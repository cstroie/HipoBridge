#!/usr/bin/env python3
"""
Client script to interact with the HippoBridge API
Performs login (if needed) and patient search operations

Copyright (C) 2024 Costin Stroie <costinstroie@eridu.eu.org>

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
import json

# Configuration
BASE_URL = "http://localhost:44660"

# Simple in-memory cache for CNP to patient code mappings
cnp_cache = {}
cache_max_size = 1000  # Maximum number of entries to cache

# FHIR resource types
FHIR_PATIENT = "Patient"
FHIR_BUNDLE = "Bundle"

async def _make_api_request(session: aiohttp.ClientSession, method: str, url: str, data: dict = None) -> tuple:
    """Make an API request and return the response data and success status.
    
    Args:
        session (aiohttp.ClientSession): The HTTP session to use for the request
        method (str): HTTP method ("GET" or "POST")
        url (str): The URL to request
        data (dict, optional): Data to send with POST requests
        
    Returns:
        tuple: (data, success) where data is the response data and success is a boolean
    """
    try:
        if method == "GET":
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data, True
                else:
                    data = await response.json()
                    return data, False
        else:  # POST
            async with session.post(url, json=data) as response:
                if response.status == 200:
                    data = await response.json()
                    return data, True
                else:
                    data = await response.json()
                    return data, False
    except Exception as e:
        return {"status": "error", "message": str(e)}, False

async def _print_response_result(operation: str, data: dict, success: bool) -> bool:
    """Print the result of an API operation and return success status.
    
    Args:
        operation (str): The name of the operation (e.g., "Login", "Patient search")
        data (dict): The response data
        success (bool): Whether the request was successful
        
    Returns:
        bool: True if operation was successful, False otherwise
    """
    if success:
        message = data.get('message', 'No message')
        print(f"{operation} successful: {message}")
        return True
    else:
        message = data.get('message', 'No message')
        status = data.get('status', 'unknown')
        print(f"{operation} failed: {message} (status: {status})")
        return False

async def login(session: aiohttp.ClientSession, username: str, password: str) -> bool:
    """Perform login to the HippoBridge API.
    
    Makes a POST request to the FHIR API login endpoint with the provided credentials.
    
    Args:
        session (aiohttp.ClientSession): The HTTP session to use for the request
        username (str): Username for authentication
        password (str): Password for authentication
        
    Returns:
        bool: True if login was successful, False otherwise
    """
    print(f"Logging in as {username}...")
    
    login_data = {
        "username": username,
        "password": password
    }
    
    data, success = await _make_api_request(session, "POST", f"{BASE_URL}/fhir/login", login_data)
    
    if success and data.get("status") == "success":
        print(f"Login successful: {data.get('message', 'No message')}")
        return True
    else:
        print(f"Login failed: {data.get('message', 'No message')}")
        return False

async def search_patients(session: aiohttp.ClientSession, search_term: str, fhir_format: bool = False) -> bool:
    """Search for patients using the FHIR API.
    
    Performs a patient search on the HippoBridge service using the provided search term.
    Returns FHIR Patient resources or Bundle.
    
    Args:
        session (aiohttp.ClientSession): The HTTP session to use for the request
        search_term (str): The term to search for (patient name, CNP, etc.)
        fhir_format (bool): Whether to request FHIR format (default: False)
        
    Returns:
        bool: True if search was successful, False otherwise
    """
    print(f"Searching for patients with term: '{search_term}'")
    
    headers = {}
    if fhir_format:
        headers["Accept"] = "application/fhir+json"
    
    try:
        async with session.get(f"{BASE_URL}/fhir/Patient?q={search_term}", headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                # Handle FHIR response
                if data.get("resourceType") == FHIR_BUNDLE:
                    print(f"Patient search successful! Found {data.get('total', 0)} patients (FHIR Bundle)")
                    entries = data.get("entry", [])
                    for i, entry in enumerate(entries, 1):
                        patient = entry.get("resource", {})
                        patient_id = patient.get("id", "N/A")
                        names = patient.get("name", [])
                        display_name = "Unknown"
                        if names:
                            name = names[0]
                            given = " ".join(name.get("given", []))
                            family = name.get("family", "")
                            display_name = f"{given} {family}".strip() or "Unknown"
                        print(f"  {i}. {display_name} (ID: {patient_id})")
                elif data.get("resourceType") == FHIR_PATIENT:
                    print("Patient search successful! Found single patient (FHIR Patient)")
                    names = data.get("name", [])
                    display_name = "Unknown"
                    if names:
                        name = names[0]
                        given = " ".join(name.get("given", []))
                        family = name.get("family", "")
                        display_name = f"{given} {family}".strip() or "Unknown"
                    patient_id = data.get("id", "N/A")
                    print(f"  Patient: {display_name} (ID: {patient_id})")
                return True
            else:
                data = await response.json()
                print(f"Patient search failed: {data.get('message', 'No message')}")
                return False
    except Exception as e:
        print(f"Patient search failed: {str(e)}")
        return False

async def get_report(session: aiohttp.ClientSession, report_id: str) -> bool:
    """Retrieve a report by ID using the FHIR API.
    
    Gets a report from the HippoBridge service and displays the parsed data.
    Returns FHIR DiagnosticReport resource.
    
    Args:
        session (aiohttp.ClientSession): The HTTP session to use for the request
        report_id (str): The ID of the report to retrieve
        
    Returns:
        bool: True if retrieval was successful, False otherwise
    """
    print(f"Retrieving report with ID: {report_id}")
    
    data, success = await _make_api_request(session, "GET", f"{BASE_URL}/fhir/DiagnosticReport/{report_id}")
    
    if not success:
        print(f"Report retrieval failed")
        return False
    
    print("Report retrieval successful!")
    
    # Display FHIR DiagnosticReport data
    print("\n--- Diagnostic Report Data ---")
    if data.get("id"):
        print(f"Report ID: {data['id']}")
    if data.get("status"):
        print(f"Status: {data['status']}")
    if data.get("effectiveDateTime"):
        print(f"Effective Date/Time: {data['effectiveDateTime']}")
    
    # Display code information
    if data.get("code"):
        code = data["code"]
        if code.get("text"):
            print(f"Report Type: {code['text']}")
        elif code.get("coding"):
            coding = code["coding"][0] if code["coding"] else {}
            if coding.get("display"):
                print(f"Report Type: {coding['display']}")
    
    # Display subject (patient) reference
    if data.get("subject"):
        subject = data["subject"]
        if subject.get("reference"):
            print(f"Patient Reference: {subject['reference']}")
    
    # Display performer information
    if data.get("performer"):
        performers = data["performer"]
        if performers:
            performer = performers[0]
            if performer.get("display"):
                print(f"Performer: {performer['display']}")
    
    # Display conclusion
    if data.get("conclusion"):
        print(f"\nConclusion: {data['conclusion']}")
    
    # Display results
    if data.get("result"):
        results = data["result"]
        print(f"\nResults ({len(results)} found):")
        for i, result in enumerate(results, 1):
            if result.get("reference"):
                print(f"  {i}. {result['reference']}")
    
    print("--------------------------")
    
    return True


async def get_imaging_study(session: aiohttp.ClientSession, study_id: str) -> bool:
    """Retrieve an imaging study by ID using the FHIR API.
    
    Gets an imaging study from the HippoBridge service and displays the parsed data.
    Returns FHIR ImagingStudy resource.
    
    Args:
        session (aiohttp.ClientSession): The HTTP session to use for the request
        study_id (str): The ID of the imaging study to retrieve
        
    Returns:
        bool: True if retrieval was successful, False otherwise
    """
    print(f"Retrieving imaging study with ID: {study_id}")
    
    data, success = await _make_api_request(session, "GET", f"{BASE_URL}/fhir/ImagingStudy/{study_id}")
    
    if not success:
        print(f"Imaging study retrieval failed")
        return False
    
    print("Imaging study retrieval successful!")
    
    # Display FHIR ImagingStudy data
    print("\n--- Imaging Study Data ---")
    if data.get("id"):
        print(f"Study ID: {data['id']}")
    if data.get("status"):
        print(f"Status: {data['status']}")
    if data.get("started"):
        print(f"Started: {data['started']}")
    
    # Display modality information
    if data.get("modality"):
        modality = data["modality"]
        if modality.get("display"):
            print(f"Modality: {modality['display']}")
        elif modality.get("code"):
            print(f"Modality: {modality['code']}")
    
    # Display subject (patient) reference
    if data.get("subject"):
        subject = data["subject"]
        if subject.get("reference"):
            print(f"Patient Reference: {subject['reference']}")
    
    # Display description
    if data.get("description"):
        print(f"Description: {data['description']}")
    
    # Display performer information
    if data.get("performer"):
        performers = data["performer"]
        print(f"\nPerformers ({len(performers)} found):")
        for i, performer in enumerate(performers, 1):
            if performer.get("actor") and performer["actor"].get("display"):
                print(f"  {i}. {performer['actor']['display']}")
    
    # Display referrer information
    if data.get("referrer"):
        referrer = data["referrer"]
        if referrer.get("display"):
            print(f"Referrer: {referrer['display']}")
    
    # Display reason
    if data.get("reason"):
        reasons = data["reason"]
        print(f"\nReasons ({len(reasons)} found):")
        for i, reason in enumerate(reasons, 1):
            if reason.get("text"):
                print(f"  {i}. {reason['text']}")
    
    # Display note
    if data.get("note"):
        notes = data["note"]
        print(f"\nNotes ({len(notes)} found):")
        for i, note in enumerate(notes, 1):
            if note.get("text"):
                print(f"  {i}. {note['text']}")
    
    # Display series information
    if data.get("series"):
        series_list = data["series"]
        print(f"\nSeries ({len(series_list)} found):")
        for i, series in enumerate(series_list, 1):
            print(f"  {i}. Series Number: {series.get('number', 'N/A')}")
            if series.get("description"):
                print(f"      Description: {series['description']}")
            if series.get("modality"):
                modality = series["modality"]
                if modality.get("display"):
                    print(f"      Modality: {modality['display']}")
                elif modality.get("code"):
                    print(f"      Modality: {modality['code']}")
    
    print("--------------------------")
    
    return True

async def get_checkout(session: aiohttp.ClientSession, checkout_id: str) -> bool:
    """Retrieve checkout information by ID using the FHIR API.
    
    Gets checkout information from the HippoBridge service and displays the parsed data.
    Returns FHIR Encounter resource.
    
    Args:
        session (aiohttp.ClientSession): The HTTP session to use for the request
        checkout_id (str): The ID of the checkout to retrieve
        
    Returns:
        bool: True if retrieval was successful, False otherwise
    """
    print(f"Retrieving checkout with ID: {checkout_id}")
    
    data, success = await _make_api_request(session, "GET", f"{BASE_URL}/fhir/Encounter?identifier={checkout_id}")
    
    if not success:
        print(f"Checkout retrieval failed")
        return False
    
    print("Checkout retrieval successful!")
    
    # Display FHIR Encounter data
    print("\n--- Encounter Data ---")
    if data.get("id"):
        print(f"Encounter ID: {data['id']}")
    if data.get("status"):
        print(f"Status: {data['status']}")
    
    # Display class information
    if data.get("class"):
        encounter_class = data["class"]
        if encounter_class.get("display"):
            print(f"Class: {encounter_class['display']}")
    
    # Display type information
    if data.get("type"):
        types = data["type"]
        if types:
            encounter_type = types[0]
            if encounter_type.get("coding"):
                coding = encounter_type["coding"][0] if encounter_type["coding"] else {}
                if coding.get("display"):
                    print(f"Type: {coding['display']}")
    
    # Display subject (patient) reference
    if data.get("subject"):
        subject = data["subject"]
        if subject.get("reference"):
            print(f"Patient Reference: {subject['reference']}")
    
    # Display participant (performer) information
    if data.get("participant"):
        participants = data["participant"]
        for participant in participants:
            if participant.get("individual"):
                individual = participant["individual"]
                if individual.get("display"):
                    print(f"Participant: {individual['display']}")
    
    # Display reason (admission diagnostic)
    if data.get("reasonCode"):
        reasons = data["reasonCode"]
        for reason in reasons:
            if reason.get("text"):
                print(f"Reason: {reason['text']}")
    
    # Display diagnosis
    if data.get("diagnosis"):
        diagnoses = data["diagnosis"]
        for diagnosis in diagnoses:
            if diagnosis.get("condition"):
                condition = diagnosis["condition"]
                if condition.get("display"):
                    print(f"Diagnosis: {condition['display']}")
    
    # Display text (epicrisis)
    if data.get("text"):
        text = data["text"]
        if text.get("div"):
            print(f"Text: {text['div']}")
    
    # Display notes
    if data.get("note"):
        notes = data["note"]
        for note in notes:
            if note.get("text"):
                print(f"Note: {note['text']}")
    
    print("--------------------------")
    
    return True

async def get_patient_code_from_cnp(session: aiohttp.ClientSession, cnp: str) -> str:
    """Get patient code by validating CNP and searching for the patient.
    
    Validates a Romanian CNP and then searches for the corresponding patient
    to retrieve their patient code using FHIR endpoints. Uses caching to avoid repeated lookups.
    
    Args:
        session (aiohttp.ClientSession): The HTTP session to use for requests
        cnp (str): The Romanian CNP to validate and search for
        
    Returns:
        str: The patient code if found, None otherwise
    """
    # Check cache first
    if cnp in cnp_cache:
        print(f"Found patient code for CNP {cnp} in cache")
        return cnp_cache[cnp]
    
    # First validate the CNP
    data, success = await _make_api_request(session, "GET", f"{BASE_URL}/fhir/ValueSet/cnp?id={cnp}")
    
    if not success or not data.get("valid"):
        print(f"CNP {cnp} is not valid")
        return None
    
    print(f"CNP {cnp} is valid, searching for patient...")
    
    # Search for the patient using the CNP
    data, success = await _make_api_request(session, "GET", f"{BASE_URL}/fhir/Patient?q={cnp}")
    
    if not success:
        print(f"Patient search failed")
        return None
    
    # Handle FHIR response
    if data.get("resourceType") == FHIR_BUNDLE:
        entries = data.get("entry", [])
        if entries:
            # Use the first patient's code
            patient = entries[0].get("resource", {})
            patient_code = patient.get("id")
            if patient_code:
                print(f"Found patient code: {patient_code} (first of {len(entries)} matches)")
                # Cache the result
                if len(cnp_cache) < cache_max_size:
                    cnp_cache[cnp] = patient_code
                return patient_code
        print("No patient code found in search results")
        return None
    elif data.get("resourceType") == FHIR_PATIENT:
        patient_code = data.get("id")
        if patient_code:
            print(f"Found patient code: {patient_code}")
            # Cache the result
            if len(cnp_cache) < cache_max_size:
                cnp_cache[cnp] = patient_code
            return patient_code
        else:
            print("Patient code not found in search results")
            return None
    else:
        print("Unexpected search result type")
        return None

async def search_patient_code_by_partial_cnp(session: aiohttp.ClientSession, partial_cnp: str) -> str:
    """Search for patient code using partial CNP.
    
    Searches for patients using a partial CNP and returns the patient code
    of the first match if found using FHIR endpoints.
    
    Args:
        session (aiohttp.ClientSession): The HTTP session to use for requests
        partial_cnp (str): The partial CNP to search for (without the asterisk)
        
    Returns:
        str: The patient code if found, None otherwise
    """
    print(f"Searching for patient with partial CNP: {partial_cnp}")
    
    # Search for the patient using the partial CNP
    data, success = await _make_api_request(session, "GET", f"{BASE_URL}/fhir/Patient?q={partial_cnp}")
    
    if not success:
        print(f"Patient search failed")
        return None
    
    # Handle FHIR response
    if data.get("resourceType") == FHIR_BUNDLE:
        entries = data.get("entry", [])
        if entries:
            # Use the first patient's code
            patient = entries[0].get("resource", {})
            patient_code = patient.get("id")
            if patient_code:
                print(f"Found patient code: {patient_code} (first of {len(entries)} matches)")
                return patient_code
        print("No patient code found in search results")
        return None
    elif data.get("resourceType") == FHIR_PATIENT:
        patient_code = data.get("id")
        if patient_code:
            print(f"Found patient code: {patient_code}")
            return patient_code
        else:
            print("Patient code not found in search results")
            return None
    else:
        print("Unexpected search result type")
        return None

async def get_patient(session: aiohttp.ClientSession, patient_id: str) -> bool:
    """Retrieve patient information by ID using the FHIR API.
    
    Gets patient information from the HippoBridge service. If a 13-digit CNP is provided,
    it will be validated and converted to a patient code before retrieval. If the ID ends
    with *, it's treated as a partial CNP and searched for. Returns FHIR Patient resource.
    
    Args:
        session (aiohttp.ClientSession): The HTTP session to use for the request
        patient_id (str): The patient ID, CNP, or partial CNP to retrieve
        
    Returns:
        bool: True if retrieval was successful, False otherwise
    """
    # Process patient ID (CNP validation, partial CNP search)
    processed_id = await _process_patient_id(session, patient_id)
    if processed_id:
        patient_id = processed_id
        print(f"Using patient code {patient_id} for retrieval")
    
    print(f"Retrieving patient with ID: {patient_id}")
    
    data, success = await _make_api_request(session, "GET", f"{BASE_URL}/fhir/Patient/{patient_id}")
    
    if not success:
        print(f"Patient retrieval failed")
        return False
    
    print("Patient retrieval successful!")
    
    # Display FHIR Patient data
    print("\n--- Patient Data ---")
    if data.get("id"):
        print(f"Patient ID: {data['id']}")
    
    # Display identifiers
    if data.get("identifier"):
        identifiers = data["identifier"]
        for identifier in identifiers:
            if identifier.get("system") and identifier.get("value"):
                system = identifier["system"]
                value = identifier["value"]
                if "cnp" in system:
                    print(f"CNP: {value}")
                elif "patient-code" in system:
                    print(f"Patient Code: {value}")
                else:
                    print(f"Identifier ({system}): {value}")
    
    # Display name
    if data.get("name"):
        names = data["name"]
        for name in names:
            if name.get("given") and name.get("family"):
                given = " ".join(name["given"])
                family = name["family"]
                print(f"Name: {given} {family}")
    
    # Display gender
    if data.get("gender"):
        print(f"Gender: {data['gender']}")
    
    # Display birth date
    if data.get("birthDate"):
        print(f"Birth Date: {data['birthDate']}")
    
    # Display extensions (checkin/checkout IDs)
    checkin_ids = []
    checkout_ids = []
    if data.get("extension"):
        extensions = data["extension"]
        for extension in extensions:
            if extension.get("url") and extension.get("valueString"):
                url = extension["url"]
                value = extension["valueString"]
                if "checkin-ids" in url:
                    checkin_ids = value.split(",") if value else []
                elif "checkout-ids" in url:
                    checkout_ids = value.split(",") if value else []
    
    if checkout_ids:
        print(f"\nCheckout IDs ({len(checkout_ids)} found):")
        for i, checkout_id in enumerate(checkout_ids, 1):
            print(f"  {i}. {checkout_id}")
    else:
        print("\nNo checkout IDs found")
    
    if checkin_ids:
        print(f"\nCheckin IDs ({len(checkin_ids)} found):")
        for i, checkin_id in enumerate(checkin_ids, 1):
            print(f"  {i}. {checkin_id}")
    else:
        print("\nNo checkin IDs found")
    
    print("--------------------------")
    
    return True

async def get_analyses(session: aiohttp.ClientSession, patient_id: str, analysis_type: str = None, datetime_filter: str = None) -> bool:
    """Retrieve all analyses for a patient by ID using the FHIR API.
    
    Gets all analyses for a specific patient from the HippoBridge service.
    If a 13-digit CNP is provided, it will be validated and converted to 
    a patient code before retrieval. If the ID ends with *, it's treated as
    a partial CNP and searched for. For imaging analyses (radio, ct, irm, eco),
    the corresponding reports will be automatically retrieved and displayed.
    Returns FHIR Bundle of Observation resources.
    
    Args:
        session (aiohttp.ClientSession): The HTTP session to use for the request
        patient_id (str): The patient ID, CNP, or partial CNP to retrieve analyses for
        analysis_type (str, optional): Analysis type to filter by (e.g., radio, ct, irm, eco, lab)
        datetime_filter (str, optional): Date/time filter in ISO format (YYYY-MM-DDTHH:mm:ss)
        
    Returns:
        bool: True if retrieval was successful, False otherwise
    """
    # Process patient ID (CNP validation, partial CNP search)
    processed_id = await _process_patient_id(session, patient_id)
    if processed_id:
        patient_id = processed_id
        print(f"Using patient code {patient_id} for analyses retrieval")
    
    # Build URL with optional parameters
    url = f"{BASE_URL}/fhir/Observation?patient={patient_id}"
    if analysis_type:
        url += f"&type={analysis_type}"
    if datetime_filter:
        url += f"&dt={datetime_filter}"
    
    print(f"Retrieving analyses for patient with ID: {patient_id}")
    if analysis_type:
        print(f"Filtering by analysis type: {analysis_type}")
    if datetime_filter:
        print(f"Filtering by datetime: {datetime_filter}")
    
    data, success = await _make_api_request(session, "GET", url)
    
    if not success:
        print(f"Analyses retrieval failed")
        return False
    
    print("Analyses retrieval successful!")
    
    # Handle FHIR Bundle of Observations
    if data.get("resourceType") == FHIR_BUNDLE:
        entries = data.get("entry", [])
        print(f"\nAnalyses ({len(entries)} found):")
        
        imaging_analyses = []
        for i, entry in enumerate(entries, 1):
            observation = entry.get("resource", {})
            observation_id = observation.get("id", "N/A")
            
            # Extract analysis type from code
            analysis_type = "unknown"
            if observation.get("code"):
                code = observation["code"]
                if code.get("coding"):
                    coding = code["coding"][0] if code["coding"] else {}
                    analysis_type = coding.get("code", "unknown")
            
            print(f"  {i}. ID: {observation_id} - Type: {analysis_type}")
            
            # Check if this is an imaging analysis that needs report retrieval
            if analysis_type in ['radio', 'ct', 'irm', 'eco']:
                imaging_analyses.append(observation_id)
        
        # Retrieve reports for imaging analyses
        if imaging_analyses:
            print(f"\nRetrieving reports for {len(imaging_analyses)} imaging analyses:")
            for observation_id in imaging_analyses:
                print(f"\n--- Report for Observation {observation_id} ---")
                await get_report(session, observation_id)
    else:
        print("\nNo analyses found")
    
    return True

async def validate_cnp(session: aiohttp.ClientSession, cnp: str) -> bool:
    """Validate a Romanian CNP using the FHIR API.
    
    Validates a Romanian CNP (Personal Numerical Code) using the FHIR API endpoint.
    
    Args:
        session (aiohttp.ClientSession): The HTTP session to use for the request
        cnp (str): The Romanian CNP to validate
        
    Returns:
        bool: True if validation request was successful, False otherwise
    """
    print(f"Validating CNP: {cnp}")
    
    data, success = await _make_api_request(session, "GET", f"{BASE_URL}/fhir/ValueSet/cnp?id={cnp}")
    
    if not success:
        print(f"CNP validation failed")
        return False
    
    is_valid = data.get("valid", False)
    print(f"CNP validation result: {'Valid' if is_valid else 'Invalid'}")
    return True

async def _process_patient_id(session: aiohttp.ClientSession, patient_id: str) -> str:
    """Process patient ID by validating CNP or searching for partial CNP.
    
    Args:
        session (aiohttp.ClientSession): The HTTP session to use for requests
        patient_id (str): The patient ID, CNP, or partial CNP to process
        
    Returns:
        str: The processed patient code if successful, None otherwise
    """
    # Check if patient_id is a 13-digit CNP
    if patient_id.isdigit() and len(patient_id) == 13:
        print(f"Detected 13-digit ID, checking if it's a valid CNP: {patient_id}")
        patient_code = await get_patient_code_from_cnp(session, patient_id)
        if patient_code:
            return patient_code
        else:
            print("Could not resolve CNP to patient code, using original ID")
            return None
    # Check if patient_id ends with *, treat as partial CNP
    elif patient_id.endswith('*'):
        partial_cnp = patient_id[:-1]  # Remove the asterisk
        if partial_cnp:  # Make sure there's something left
            print(f"Detected partial CNP search: {partial_cnp}")
            patient_code = await search_patient_code_by_partial_cnp(session, partial_cnp)
            if patient_code:
                return patient_code
            else:
                print("Could not find patient with partial CNP, using original ID")
                return None
    return None

async def main():
    """Main function to parse arguments and run the HippoBridge client.
    
    Parses command line arguments and executes the requested operations
    (login, patient search, report retrieval, etc.).
    
    Returns:
        int: Exit code (0 for success, 1 for failure)
    """
    parser = argparse.ArgumentParser(description="HippoBridge API Client")
    parser.add_argument("--username", "-u", help="Username for login")
    parser.add_argument("--password", "-w", help="Password for login")
    parser.add_argument("--search", "-s", help="Search term for patient search")
    parser.add_argument("--fhir", "-f", action="store_true", help="Return results in FHIR format")
    parser.add_argument("--report", "-r", help="Report ID to retrieve")
    parser.add_argument("--imaging-study", "-i", help="Imaging study ID to retrieve")
    parser.add_argument("--checkout", "-o", help="Checkout ID to retrieve")
    parser.add_argument("--patient", "-p", help="Patient ID to retrieve")
    parser.add_argument("--analyses", "-a", help="Patient ID to retrieve analyses for")
    parser.add_argument("--analysis-type", "-t", help="Analysis type to filter by (e.g., radio, ct, irm, eco, lab)")
    parser.add_argument("--datetime-filter", "-d", help="Date/time filter in ISO format (YYYY-MM-DDTHH:mm:ss)")
    parser.add_argument("--cnp", "-c", help="CNP to validate")
    
    args = parser.parse_args()
    
    # Get credentials from arguments or environment variables
    username = args.username or os.getenv("HYP_USER")
    password = args.password or os.getenv("HYP_PASS")
    
    if not args.search and not args.report and not args.imaging_study and not args.checkout and not args.patient and not args.analyses and not args.cnp:
        print("Error: Either search term, report ID, imaging study ID, checkout ID, patient ID, analyses ID, or CNP is required")
        parser.print_help()
        return 1
    
    if not username or not password:
        print("Error: Username and password are required (via args or HYP_USER/HYP_PASS env vars)")
        return 1
    
    async with aiohttp.ClientSession() as session:
        # Perform login
        login_success = await login(session, username, password)
        if not login_success:
            print("Failed to login, exiting...")
            return 1
        
        # Perform patient search if requested
        if args.search:
            search_success = await search_patients(session, args.search, args.fhir)
            if not search_success:
                print("Failed to search patients")
                return 1
        
        # Retrieve report if requested
        if args.report:
            report_success = await get_report(session, args.report)
            if not report_success:
                print("Failed to retrieve report")
                return 1
        
        # Retrieve imaging study if requested
        if args.imaging_study:
            imaging_study_success = await get_imaging_study(session, args.imaging_study)
            if not imaging_study_success:
                print("Failed to retrieve imaging study")
                return 1
        
        # Retrieve checkout if requested
        if args.checkout:
            checkout_success = await get_checkout(session, args.checkout)
            if not checkout_success:
                print("Failed to retrieve checkout")
                return 1
        
        # Retrieve patient if requested
        if args.patient:
            patient_success = await get_patient(session, args.patient)
            if not patient_success:
                print("Failed to retrieve patient")
                return 1
        
        # Retrieve analyses if requested
        if args.analyses:
            analyses_success = await get_analyses(session, args.analyses, args.analysis_type, args.datetime_filter)
            if not analyses_success:
                print("Failed to retrieve analyses")
                return 1
        
        # Validate CNP if requested
        if args.cnp:
            cnp_success = await validate_cnp(session, args.cnp)
            if not cnp_success:
                print("Failed to validate CNP")
                return 1
        
        print("All operations completed successfully!")
        return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
