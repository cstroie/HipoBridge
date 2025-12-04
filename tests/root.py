#!/usr/bin/env python3
"""
Root endpoint tests for the Hipocrate API
"""
import asyncio
import aiohttp
import os
import base64

# Configuration
BASE_URL = "http://localhost:44660"
HYP_USER = os.getenv("HYP_USER")
HYP_PASS = os.getenv("HYP_PASS")

async def test_root_endpoint(session: aiohttp.ClientSession) -> bool:
    """Test the root endpoint"""
    print("Testing root endpoint...")
    try:
        # Add credentials to headers for authentication
        headers = {}
        if HYP_USER and HYP_PASS:
            credentials = base64.b64encode(f"{HYP_USER}:{HYP_PASS}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
            
        async with session.get(f"{BASE_URL}/", headers=headers) as response:
            if response.status == 200:
                content_type = response.headers.get('content-type', '')
                if 'text/html' in content_type:
                    print(f"  ✓ Root endpoint returned HTML content")
                    return True
                else:
                    print(f"  ✗ Root endpoint returned wrong content type: {content_type}")
                    return False
            else:
                print(f"  ✗ Root endpoint failed with status: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Root endpoint failed with exception: {e}")
        return False

async def test_fhir_metadata_endpoint(session: aiohttp.ClientSession) -> bool:
    """Test the FHIR metadata endpoint"""
    print("Testing FHIR metadata endpoint...")
    try:
        async with session.get(f"{BASE_URL}/fhir/Metadata") as response:
            if response.status == 200:
                data = await response.json()
                if data.get('resourceType') == 'CapabilityStatement':
                    print(f"  ✓ FHIR metadata endpoint returned CapabilityStatement")
                    return True
                else:
                    print(f"  ✗ FHIR metadata endpoint returned wrong resource type: {data.get('resourceType')}")
                    return False
            else:
                print(f"  ✗ FHIR metadata endpoint failed with status: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ FHIR metadata endpoint failed with exception: {e}")
        return False
