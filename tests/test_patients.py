#!/usr/bin/env python3
"""
Patient-related tests for the Hipocrate API
"""
import asyncio
import aiohttp
import os

# Configuration
BASE_URL = "http://localhost:44660"
HYP_USER = os.getenv("HYP_USER")
HYP_PASS = os.getenv("HYP_PASS")

async def test_patient_search_endpoint(session: aiohttp.ClientSession) -> bool:
    """Test the patient search endpoint"""
    print("Testing patient search endpoint...")
    try:
        # Test with a simple search term
        # Add credentials to headers if available
        headers = {}
        if HYP_USER and HYP_PASS:
            headers["X-Username"] = HYP_USER
            headers["X-Password"] = HYP_PASS
            
        async with session.get(f"{BASE_URL}/api/patient/search?q=test", headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                print(f"  ✓ Patient search returned status: {data.get('status', 'unknown')}")
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
        async with session.get(f"{BASE_URL}/api/patient/search") as response:
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
        async with session.get(f"{BASE_URL}/api/patient") as response:
            if response.status == 400:
                data = await response.json()
                print(f"  ✓ Patient endpoint with missing ID correctly returned 400: {data.get('message', 'unknown')}")
                return True
            else:
                print(f"  ✗ Patient endpoint with missing ID should return 400 but got: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Patient endpoint with missing ID test failed with exception: {e}")
        return False
