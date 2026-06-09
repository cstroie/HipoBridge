#!/usr/bin/env python3
"""
Patient-related tests for the Hipocrate API
"""
import asyncio
import aiohttp
import os
import base64

# Configuration
BASE_URL = "http://localhost:44660"
HYP_USER = os.getenv("HYP_USER")
HYP_PASS = os.getenv("HYP_PASS")

async def test_patient_search_endpoint(session: aiohttp.ClientSession) -> bool:
    """Test the patient search endpoint"""
    print("Testing patient search endpoint...")
    try:
        # Add credentials to headers
        headers = {}
        if HYP_USER and HYP_PASS:
            credentials = base64.b64encode(f"{HYP_USER}:{HYP_PASS}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
            
        async with session.get(f"{BASE_URL}/fhir/Patient?q=test", headers=headers) as response:
            # Accept both 200 (success) and 404 (not found but valid request)
            if response.status in [200, 404]:
                data = await response.json()
                print(f"  ✓ Patient search returned status: {data.get('resourceType', 'unknown')}")
                return True
            else:
                print(f"  ✗ Patient search failed with status: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Patient search failed with exception: {e}")
        return False

async def test_invalid_patient_search(session: aiohttp.ClientSession) -> bool:
    """Test patient search with missing term"""
    print("Testing patient search with missing term...")
    try:
        # Add credentials to headers
        headers = {}
        if HYP_USER and HYP_PASS:
            credentials = base64.b64encode(f"{HYP_USER}:{HYP_PASS}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
            
        async with session.get(f"{BASE_URL}/fhir/Patient", headers=headers) as response:
            if response.status == 400:
                data = await response.json()
                print(f"  ✓ Invalid search correctly returned 400: {data.get('message', 'unknown')}")
                return True
            else:
                print(f"  ✗ Invalid search should return 400 but got: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Invalid search test failed with exception: {e}")
        return False

async def test_patient_endpoint_missing_id(session: aiohttp.ClientSession) -> bool:
    """Test patient endpoint with missing ID"""
    print("Testing patient endpoint with missing ID...")
    try:
        # Add credentials to headers
        headers = {}
        if HYP_USER and HYP_PASS:
            credentials = base64.b64encode(f"{HYP_USER}:{HYP_PASS}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
            
        async with session.get(f"{BASE_URL}/fhir/Patient/", headers=headers) as response:
            if response.status in (400, 404):
                print(f"  ✓ Patient endpoint with missing ID correctly returned {response.status}")
                return True
            else:
                print(f"  ✗ Patient endpoint with missing ID should return 400/404 but got: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Patient endpoint with missing ID test failed with exception: {e}")
        return False
