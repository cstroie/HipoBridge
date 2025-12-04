#!/usr/bin/env python3
"""
DiagnosticReport-related tests for the Hipocrate API
"""
import asyncio
import aiohttp
import os
import base64

# Configuration
BASE_URL = "http://localhost:44660"
HYP_USER = os.getenv("HYP_USER")
HYP_PASS = os.getenv("HYP_PASS")

async def test_diagnostic_report_endpoint_missing_id(session: aiohttp.ClientSession) -> bool:
    """Test diagnostic report endpoint with missing ID"""
    print("Testing diagnostic report endpoint with missing ID...")
    try:
        # Add credentials to headers
        headers = {}
        if HYP_USER and HYP_PASS:
            credentials = base64.b64encode(f"{HYP_USER}:{HYP_PASS}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
            
        async with session.get(f"{BASE_URL}/fhir/DiagnosticReport", headers=headers) as response:
            if response.status == 400:
                data = await response.json()
                print(f"  ✓ Diagnostic report endpoint with missing ID correctly returned 400: {data.get('message', 'unknown')}")
                return True
            else:
                print(f"  ✗ Diagnostic report endpoint with missing ID should return 400 but got: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Diagnostic report endpoint with missing ID test failed with exception: {e}")
        return False
