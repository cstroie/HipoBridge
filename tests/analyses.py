#!/usr/bin/env python3
"""
Observation-related tests for the Hipocrate API
"""
import asyncio
import aiohttp
import os

# Configuration
BASE_URL = "http://localhost:44660"
HYP_USER = os.getenv("HYP_USER")
HYP_PASS = os.getenv("HYP_PASS")

async def test_observations_endpoint_missing_patient_id(session: aiohttp.ClientSession) -> bool:
    """Test observations endpoint with missing patient ID"""
    print("Testing observations endpoint with missing patient ID...")
    try:
        # Add credentials to headers
        headers = {}
        if HYP_USER and HYP_PASS:
            import base64
            credentials = base64.b64encode(f"{HYP_USER}:{HYP_PASS}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
            
        async with session.get(f"{BASE_URL}/fhir/Observation", headers=headers) as response:
            if response.status == 400:
                data = await response.json()
                print(f"  ✓ Observations endpoint with missing patient ID correctly returned 400: {data.get('message', 'unknown')}")
                return True
            else:
                print(f"  ✗ Observations endpoint with missing patient ID should return 400 but got: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Observations endpoint with missing patient ID test failed with exception: {e}")
        return False
