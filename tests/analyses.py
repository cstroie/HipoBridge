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
            
        async with session.get(f"{BASE_URL}/fhir/ServiceRequest", headers=headers) as response:
            if response.status in (400, 404):
                print(f"  ✓ ServiceRequest without patient ID correctly returned {response.status}")
                return True
            else:
                print(f"  ✗ ServiceRequest without patient ID should return 400/404 but got: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Observations endpoint with missing patient ID test failed with exception: {e}")
        return False
