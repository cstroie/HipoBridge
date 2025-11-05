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

async def main():
    """Main function to parse arguments and run the client"""
    parser = argparse.ArgumentParser(description="Hipocrate API Client")
    parser.add_argument("--username", "-u", help="Username for login")
    parser.add_argument("--password", "-p", help="Password for login")
    parser.add_argument("--search", "-s", help="Search term for patient search")
    parser.add_argument("--type", "-t", default="PA", help="Search type (default: PA)")
    
    args = parser.parse_args()
    
    # Get credentials from arguments or environment variables
    username = args.username or os.getenv("HYP_USER")
    password = args.password or os.getenv("HYP_PASS")
    
    if not args.search:
        print("Error: Search term is required")
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
        
        # Perform patient search
        search_success = await search_patients(session, args.search, args.type)
        if not search_success:
            print("Failed to search patients")
            return 1
        
        print("All operations completed successfully!")
        return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
