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

async def login(session: aiohttp.ClientSession, username: str, password: str) -> bool:
    """Perform login to the API"""
    print(f"Logging in as {username}...")
    
    login_data = {
        "username": username,
        "password": password
    }
    
    try:
        async with session.post(f"{BASE_URL}/api/login", json=login_data) as response:
            if response.status == 200:
                data = await response.json()
                print(f"Login successful: {data.get('message', 'No message')}")
                return True
            else:
                data = await response.json()
                print(f"Login failed with status {response.status}: {data.get('message', 'No message')}")
                return False
    except Exception as e:
        print(f"Login failed with exception: {e}")
        return False

async def search_patients(session: aiohttp.ClientSession, search_term: str, search_type: str = "PA") -> bool:
    """Search for patients using the API"""
    print(f"Searching for patients with term: '{search_term}' (type: {search_type})")
    
    try:
        # Make search request
        async with session.get(
            f"{BASE_URL}/api/patient/search?term={search_term}&type={search_type}"
        ) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("status") == "success":
                    print("Patient search successful!")
                    # Save response to file for inspection
                    with open("patient_search_results.html", "w") as f:
                        f.write(data.get("data", ""))
                    print("Results saved to patient_search_results.html")
                    return True
                else:
                    print(f"Patient search failed: {data.get('message', 'No message')}")
                    return False
            else:
                print(f"Patient search failed with status: {response.status}")
                return False
    except Exception as e:
        print(f"Patient search failed with exception: {e}")
        return False

async def get_report(session: aiohttp.ClientSession, report_id: str) -> bool:
    """Retrieve a report by ID using the API"""
    print(f"Retrieving report with ID: {report_id}")
    
    try:
        # Make report request
        async with session.get(
            f"{BASE_URL}/api/report?id={report_id}"
        ) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("status") == "success":
                    print(f"Report retrieval successful! (followed {data.get('redirects_followed', 0)} redirects)")
                    
                    # Save HTML response to file for inspection
                    filename = f"report_{report_id}.html"
                    with open(filename, "w") as f:
                        f.write(data.get("data", ""))
                    print(f"Full report saved to {filename}")
                    
                    # Display parsed data if available
                    parsed_data = data.get("parsed_data", {})
                    if parsed_data:
                        print("\n--- Parsed Report Data ---")
                        if parsed_data.get("patient_name"):
                            print(f"Patient Name: {parsed_data['patient_name']}")
                        if parsed_data.get("age"):
                            print(f"Age: {parsed_data['age']}")
                        if parsed_data.get("gender"):
                            print(f"Gender: {parsed_data['gender']}")
                        if parsed_data.get("patient_id"):
                            print(f"Patient ID (CNP): {parsed_data['patient_id']}")
                        if parsed_data.get("patient_code"):
                            print(f"Patient Code: {parsed_data['patient_code']}")
                        if parsed_data.get("sample_datetime"):
                            print(f"Sample Date/Time: {parsed_data['sample_datetime']}")
                        if parsed_data.get("examination"):
                            print(f"Examination: {parsed_data['examination']}")
                        
                        # Handle multiple reports
                        reports = parsed_data.get("reports", [])
                        if reports:
                            print(f"\nReports ({len(reports)} found):")
                            for i, report in enumerate(reports, 1):
                                investigation = report.get("investigation", '')
                                print(f"\nReport {i}: {report['investigation']}")
                                if report.get("result"):
                                    print(f"{report['result']}")
                        elif parsed_data.get("result"):
                            # Fallback to single result if reports list is empty
                            print(f"Result: {parsed_data['result']}")
                        
                        if parsed_data.get("examiner"):
                            print(f"\nExaminer: {parsed_data['examiner']}")
                        print("--------------------------")
                    
                    return True
                else:
                    print(f"Report retrieval failed: {data.get('message', 'No message')}")
                    return False
            else:
                print(f"Report retrieval failed with status: {response.status}")
                return False
    except Exception as e:
        print(f"Report retrieval failed with exception: {e}")
        return False

async def get_checkout(session: aiohttp.ClientSession, checkout_id: str) -> bool:
    """Retrieve checkout information by ID using the API"""
    print(f"Retrieving checkout with ID: {checkout_id}")
    
    try:
        # Make checkout request
        async with session.get(
            f"{BASE_URL}/api/checkout?id={checkout_id}"
        ) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("status") == "success":
                    print("Checkout retrieval successful!")
                    
                    # Save HTML response to file for inspection
                    filename = f"checkout_{checkout_id}.html"
                    with open(filename, "w") as f:
                        f.write(data.get("data", ""))
                    print(f"Full checkout saved to {filename}")
                    
                    # Display parsed data if available
                    parsed_data = data.get("parsed_data", {})
                    if parsed_data:
                        print("\n--- Parsed Checkout Data ---")
                        if parsed_data.get("patient_name"):
                            print(f"Patient Name: {parsed_data['patient_name']}")
                        if parsed_data.get("patient_id"):
                            print(f"Patient ID: {parsed_data['patient_id']}")
                        if parsed_data.get("admission_diagnostic"):
                            print(f"Admission Diagnostic: {parsed_data['admission_diagnostic']}")
                        if parsed_data.get("epicrisis"):
                            print(f"Epicrisis: {parsed_data['epicrisis']}")
                        if parsed_data.get("diagnostic"):
                            print(f"Diagnostic: {parsed_data['diagnostic']}")
                        if parsed_data.get("surgery"):
                            print(f"Surgery: {parsed_data['surgery']}")
                        if parsed_data.get("recommendations"):
                            print(f"Recommendations: {parsed_data['recommendations']}")
                        print("--------------------------")
                    
                    return True
                else:
                    print(f"Checkout retrieval failed: {data.get('message', 'No message')}")
                    return False
            else:
                print(f"Checkout retrieval failed with status: {response.status}")
                return False
    except Exception as e:
        print(f"Checkout retrieval failed with exception: {e}")
        return False

async def get_patient(session: aiohttp.ClientSession, patient_id: str) -> bool:
    """Retrieve patient information by ID using the API"""
    print(f"Retrieving patient with ID: {patient_id}")
    
    try:
        # Make patient request
        async with session.get(
            f"{BASE_URL}/api/patient?id={patient_id}"
        ) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("status") == "success":
                    print("Patient retrieval successful!")
                    
                    # Save HTML response to file for inspection
                    filename = f"patient_{patient_id}.html"
                    with open(filename, "w") as f:
                        f.write(data.get("data", ""))
                    print(f"Full patient data saved to {filename}")
                    
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
                else:
                    print(f"Patient retrieval failed: {data.get('message', 'No message')}")
                    return False
            else:
                print(f"Patient retrieval failed with status: {response.status}")
                return False
    except Exception as e:
        print(f"Patient retrieval failed with exception: {e}")
        return False

async def main():
    """Main function to parse arguments and run the client"""
    parser = argparse.ArgumentParser(description="Hipocrate API Client")
    parser.add_argument("--username", "-u", help="Username for login")
    parser.add_argument("--password", "-w", help="Password for login")
    parser.add_argument("--search", "-s", help="Search term for patient search")
    parser.add_argument("--type", "-t", default="PA", help="Search type (default: PA)")
    parser.add_argument("--report", "-r", help="Report ID to retrieve")
    parser.add_argument("--checkout", "-c", help="Checkout ID to retrieve")
    parser.add_argument("--patient", "-p", help="Patient ID to retrieve")
    
    args = parser.parse_args()
    
    # Get credentials from arguments or environment variables
    username = args.username or os.getenv("HYP_USER")
    password = args.password or os.getenv("HYP_PASS")
    
    if not args.search and not args.report and not args.checkout and not args.patient:
        print("Error: Either search term, report ID, checkout ID, or patient ID is required")
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
            search_success = await search_patients(session, args.search, args.type)
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
        
        print("All operations completed successfully!")
        return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
