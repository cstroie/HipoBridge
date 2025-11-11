#!/usr/bin/env python3
"""
Client script to interact with the Hipocrate API
Performs login (if needed) and patient search operations
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
    """Perform login to the Hipocrate API.
    
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
    
    Performs a patient search on the Hipocrate service using the provided search term.
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
                content_type = response.headers.get("Content-Type", "")
                if "application/fhir+json" in content_type:
                    data = await response.json()
                    # Handle FHIR response
                    if data.get("resourceType") == "Bundle":
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
                    elif data.get("resourceType") == "Patient":
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
                    if not data.get("status") == "success":
                        print(f"Patient search failed: {data.get('message', 'No message')}")
                        return False
                result_type = data.get("type", "raw")
                print(f"Patient search successful! (type: {result_type})")
            else:
                data = await response.json()
                print(f"Patient search failed: {data.get('message', 'No message')}")
                return False
    except Exception as e:
        print(f"Patient search failed: {str(e)}")
        return False
    
    # Handle non-FHIR response
    result_type = data.get("type", "raw")
    print(f"Patient search successful! (type: {result_type})")
    
    if result_type == "single_patient":
        patient_data = data.get("data", {})
        print(f"Found single patient: {patient_data.get('patient_name', 'Unknown')}")
        if patient_data.get('patient_id'):
            print(f"  Patient ID (CNP): {patient_data['patient_id']}")
        if patient_data.get('patient_code'):
            print(f"  Patient Code: {patient_data['patient_code']}")
        if patient_data.get('presentations'):
            presentations = patient_data['presentations']
            print(f"  Presentations ({len(presentations)} found):")
            for i, pres_id in enumerate(presentations, 1):
                print(f"    {i}. {pres_id}")
        if patient_data.get('checkins'):
            checkins = patient_data['checkins']
            print(f"  Checkins ({len(checkins)} found):")
            for i, checkin_id in enumerate(checkins, 1):
                print(f"    {i}. {checkin_id}")
        if patient_data.get('checkouts'):
            checkouts = patient_data['checkouts']
            print(f"  Checkouts ({len(checkouts)} found):")
            for i, checkout_id in enumerate(checkouts, 1):
                print(f"    {i}. {checkout_id}")
        return True
    elif result_type == "multiple_patients":
        patients = data.get("data", [])
        print(f"Found {len(patients)} patients:")
        for i, patient in enumerate(patients, 1):
            print(f"  {i}. {patient.get('patient_name', 'Unknown')} (Code: {patient.get('patient_code', 'N/A')})")
        return True
    else:
        # Save raw response to file for inspection
        with open("patient_search_results.html", "w") as f:
            f.write(data.get("data", ""))
        print("Results saved to patient_search_results.html")
        return True

async def get_report(session: aiohttp.ClientSession, report_id: str) -> bool:
    """Retrieve a report by ID using the FHIR API.
    
    Gets a report from the Hipocrate service and displays the parsed data.
    Returns FHIR DiagnosticReport resource.
    
    Args:
        session (aiohttp.ClientSession): The HTTP session to use for the request
        report_id (str): The ID of the report to retrieve
        
    Returns:
        bool: True if retrieval was successful, False otherwise
    """
    print(f"Retrieving report with ID: {report_id}")
    
    data, success = await _make_api_request(session, "GET", f"{BASE_URL}/fhir/DiagnosticReport?identifier={report_id}")
    
    if not success or data.get("status") != "success":
        print(f"Report retrieval failed: {data.get('message', 'No message')}")
        return False
    
    print(f"Report retrieval successful! (followed {data.get('redirects_followed', 0)} redirects)")
    
    # Display parsed data if available
    print("\n--- Parsed Report Data ---")
    if data.get("patient_name"):
        print(f"Patient Name: {data['patient_name']}")
    if data.get("age"):
        print(f"Age: {data['age']}")
    if data.get("gender"):
        print(f"Gender: {data['gender']}")
    if data.get("patient_id"):
        print(f"Patient ID (CNP): {data['patient_id']}")
    if data.get("patient_code"):
        print(f"Patient Code: {data['patient_code']}")
    if data.get("sample_datetime"):
        print(f"Sample Date/Time: {data['sample_datetime']}")
    if data.get("examination"):
        print(f"Examination: {data['examination']}")
    
    # Handle multiple reports
    reports = data.get("reports", [])
    if reports:
        print(f"\nReports ({len(reports)} found):")
        for i, report in enumerate(reports, 1):
            investigation = report.get("investigation", '')
            print(f"\nReport {i}: {report['investigation']}")
            if report.get("result"):
                print(f"{report['result']}")
    elif data.get("result"):
        # Fallback to single result if reports list is empty
        print(f"Result: {data['result']}")
    
    if data.get("examiner"):
        print(f"\nExaminer: {data['examiner']}")
    print("--------------------------")
    
    return True

async def get_checkout(session: aiohttp.ClientSession, checkout_id: str) -> bool:
    """Retrieve checkout information by ID using the FHIR API.
    
    Gets checkout information from the Hipocrate service and displays the parsed data.
    Returns FHIR Encounter resource.
    
    Args:
        session (aiohttp.ClientSession): The HTTP session to use for the request
        checkout_id (str): The ID of the checkout to retrieve
        
    Returns:
        bool: True if retrieval was successful, False otherwise
    """
    print(f"Retrieving checkout with ID: {checkout_id}")
    
    data, success = await _make_api_request(session, "GET", f"{BASE_URL}/fhir/Encounter?identifier={checkout_id}")
    
    if not success or data.get("status") != "success":
        print(f"Checkout retrieval failed: {data.get('message', 'No message')}")
        return False
    
    print("Checkout retrieval successful!")
    
    # Display parsed data if available
    print("\n--- Parsed Checkout Data ---")
    if data.get("patient_name"):
        print(f"Patient Name: {data['patient_name']}")
    if data.get("patient_id"):
        print(f"Patient ID: {data['patient_id']}")
    if data.get("admission_diagnostic"):
        print(f"Admission Diagnostic: {data['admission_diagnostic']}")
    if data.get("epicrisis"):
        print(f"Epicrisis: {data['epicrisis']}")
    if data.get("diagnostic"):
        print(f"Diagnostic: {data['diagnostic']}")
    if data.get("surgery"):
        print(f"Surgery: {data['surgery']}")
    if data.get("recommendations"):
        print(f"Recommendations: {data['recommendations']}")
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
    # First validate the CNP
    data, success = await _make_api_request(session, "GET", f"{BASE_URL}/fhir/ValueSet/cnp?id={cnp}")
    
    if not success or data.get("status") != "success" or not data.get("valid"):
        print(f"CNP {cnp} is not valid")
        return None
    
    print(f"CNP {cnp} is valid, searching for patient...")
    
    # Search for the patient using the CNP
    data, success = await _make_api_request(session, "GET", f"{BASE_URL}/fhir/Patient?q={cnp}")
    
    if not success or data.get("status") != "success":
        print(f"Patient search failed: {data.get('message', 'No message')}")
        return None
    
    result_type = data.get("type")
    if result_type == "single_patient":
        patient_data = data.get("data", {})
        patient_code = patient_data.get("patient_code")
        if patient_code:
            print(f"Found patient code: {patient_code}")
            return patient_code
        else:
            print("Patient code not found in search results")
            return None
    elif result_type == "multiple_patients":
        patients = data.get("data", [])
        if patients:
            # Use the first patient's code
            patient_code = patients[0].get("patient_code")
            if patient_code:
                print(f"Found patient code: {patient_code} (first of {len(patients)} matches)")
                return patient_code
        print("No patient code found in search results")
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
    
    if not success or data.get("status") != "success":
        print(f"Patient search failed: {data.get('message', 'No message')}")
        return None
    
    result_type = data.get("type")
    if result_type == "single_patient":
        patient_data = data.get("data", {})
        patient_code = patient_data.get("patient_code")
        if patient_code:
            print(f"Found patient code: {patient_code}")
            return patient_code
        else:
            print("Patient code not found in search results")
            return None
    elif result_type == "multiple_patients":
        patients = data.get("data", [])
        if patients:
            # Use the first patient's code
            patient_code = patients[0].get("patient_code")
            if patient_code:
                print(f"Found patient code: {patient_code} (first of {len(patients)} matches)")
                return patient_code
        print("No patient code found in search results")
        return None
    else:
        print("Unexpected search result type")
        return None

async def get_patient(session: aiohttp.ClientSession, patient_id: str) -> bool:
    """Retrieve patient information by ID using the FHIR API.
    
    Gets patient information from the Hipocrate service. If a 13-digit CNP is provided,
    it will be validated and converted to a patient code before retrieval. If the ID ends
    with *, it's treated as a partial CNP and searched for. Returns FHIR Patient resource.
    
    Args:
        session (aiohttp.ClientSession): The HTTP session to use for the request
        patient_id (str): The patient ID, CNP, or partial CNP to retrieve
        
    Returns:
        bool: True if retrieval was successful, False otherwise
    """
    # Check if patient_id is a 13-digit CNP
    if patient_id.isdigit() and len(patient_id) == 13:
        print(f"Detected 13-digit ID, checking if it's a valid CNP: {patient_id}")
        patient_code = await get_patient_code_from_cnp(session, patient_id)
        if patient_code:
            patient_id = patient_code
            print(f"Using patient code {patient_id} for retrieval")
        else:
            print("Could not resolve CNP to patient code, using original ID")
    # Check if patient_id ends with *, treat as partial CNP
    elif patient_id.endswith('*'):
        partial_cnp = patient_id[:-1]  # Remove the asterisk
        if partial_cnp:  # Make sure there's something left
            print(f"Detected partial CNP search: {partial_cnp}")
            patient_code = await search_patient_code_by_partial_cnp(session, partial_cnp)
            if patient_code:
                patient_id = patient_code
                print(f"Using patient code {patient_id} for retrieval")
            else:
                print("Could not find patient with partial CNP, using original ID")
    
    print(f"Retrieving patient with ID: {patient_id}")
    
    data, success = await _make_api_request(session, "GET", f"{BASE_URL}/fhir/Patient/{patient_id}")
    
    if not success or data.get("status") != "success":
        print(f"Patient retrieval failed: {data.get('message', 'No message')}")
        return False
    
    print("Patient retrieval successful!")
    
    # Display associated checkout and checkin IDs
    checkout_ids = data.get("checkout_ids", [])
    checkin_ids = data.get("checkin_ids", [])
    
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
    
    return True

async def get_analyses(session: aiohttp.ClientSession, patient_id: str, analysis_type: str = None, datetime_filter: str = None) -> bool:
    """Retrieve all analyses for a patient by ID using the FHIR API.
    
    Gets all analyses for a specific patient from the Hipocrate service.
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
    # Check if patient_id is a 13-digit CNP
    if patient_id.isdigit() and len(patient_id) == 13:
        print(f"Detected 13-digit ID, checking if it's a valid CNP: {patient_id}")
        patient_code = await get_patient_code_from_cnp(session, patient_id)
        if patient_code:
            patient_id = patient_code
            print(f"Using patient code {patient_id} for analyses retrieval")
        else:
            print("Could not resolve CNP to patient code, using original ID")
    # Check if patient_id ends with *, treat as partial CNP
    elif patient_id.endswith('*'):
        partial_cnp = patient_id[:-1]  # Remove the asterisk
        if partial_cnp:  # Make sure there's something left
            print(f"Detected partial CNP search: {partial_cnp}")
            patient_code = await search_patient_code_by_partial_cnp(session, partial_cnp)
            if patient_code:
                patient_id = patient_code
                print(f"Using patient code {patient_id} for analyses retrieval")
            else:
                print("Could not find patient with partial CNP, using original ID")
    
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
    
    if not success or data.get("status") != "success":
        print(f"Analyses retrieval failed: {data.get('message', 'No message')}")
        return False
    
    print("Analyses retrieval successful!")
    
    # Display patient name and analyses
    patient_name = data.get("patient_name", "")
    if patient_name:
        print(f"Patient: {patient_name}")
    
    analyses = data.get("analyses", [])
    
    if analyses:
        print(f"\nAnalyses ({len(analyses)} found):")
        imaging_analyses = []
        for i, analysis in enumerate(analyses, 1):
            analysis_type = analysis.get('type', 'unknown')
            print(f"  {i}. ID: {analysis.get('report_id', 'N/A')} - Type: {analysis_type}")
            
            # Check if this is an imaging analysis that needs report retrieval
            if analysis_type in ['radio', 'ct', 'irm', 'eco']:
                imaging_analyses.append(analysis)
        
        # Retrieve reports for imaging analyses
        if imaging_analyses:
            print(f"\nRetrieving reports for {len(imaging_analyses)} imaging analyses:")
            for analysis in imaging_analyses:
                report_id = analysis.get('report_id')
                analysis_type = analysis.get('type')
                print(f"\n--- Report for {analysis_type.upper()} (ID: {report_id}) ---")
                await get_report(session, report_id)
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
    
    if not success or data.get("status") != "success":
        print(f"CNP validation failed: {data.get('message', 'No message')}")
        return False
    
    is_valid = data.get("valid", False)
    print(f"CNP validation result: {'Valid' if is_valid else 'Invalid'}")
    return True

async def main():
    """Main function to parse arguments and run the client.
    
    Parses command line arguments and executes the requested operations
    (login, patient search, report retrieval, etc.).
    
    Returns:
        int: Exit code (0 for success, 1 for failure)
    """
    parser = argparse.ArgumentParser(description="Hipocrate API Client")
    parser.add_argument("--username", "-u", help="Username for login")
    parser.add_argument("--password", "-w", help="Password for login")
    parser.add_argument("--search", "-s", help="Search term for patient search")
    parser.add_argument("--fhir", "-f", action="store_true", help="Return results in FHIR format")
    parser.add_argument("--report", "-r", help="Report ID to retrieve")
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
    
    if not args.search and not args.report and not args.checkout and not args.patient and not args.analyses and not args.cnp:
        print("Error: Either search term, report ID, checkout ID, patient ID, analyses ID, or CNP is required")
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
