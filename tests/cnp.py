#!/usr/bin/env python3
"""
CNP validation tests for the Hipocrate API
"""
import asyncio
import aiohttp
import os
import base64

# Configuration
BASE_URL = "http://localhost:44660"
HYP_USER = os.getenv("HYP_USER")
HYP_PASS = os.getenv("HYP_PASS")

async def test_cnp_validation_endpoint(session: aiohttp.ClientSession) -> bool:
    """Test the CNP validation endpoint"""
    print("Testing CNP validation endpoint...")
    try:
        # Add credentials to headers
        headers = {}
        if HYP_USER and HYP_PASS:
            credentials = base64.b64encode(f"{HYP_USER}:{HYP_PASS}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
        
        # Test with a valid format CNP (but not necessarily valid)
        async with session.get(f"{BASE_URL}/fhir/ValueSet/cnp?id=1234567890123", headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                print(f"  ✓ CNP validation returned status: {data.get('status', 'unknown')}")
                return True
            else:
                print(f"  ✗ CNP validation failed with status: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ CNP validation failed with exception: {e}")
        return False

async def test_cnp_validation_missing_id(session: aiohttp.ClientSession) -> bool:
    """Test CNP validation with missing ID"""
    print("Testing CNP validation with missing ID...")
    try:
        # Add credentials to headers
        headers = {}
        if HYP_USER and HYP_PASS:
            credentials = base64.b64encode(f"{HYP_USER}:{HYP_PASS}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
            
        async with session.get(f"{BASE_URL}/fhir/ValueSet/cnp", headers=headers) as response:
            if response.status == 400:
                data = await response.json()
                print(f"  ✓ CNP validation with missing ID correctly returned 400: {data.get('message', 'unknown')}")
                return True
            else:
                print(f"  ✗ CNP validation with missing ID should return 400 but got: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ CNP validation with missing ID test failed with exception: {e}")
        return False
