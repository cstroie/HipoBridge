#!/usr/bin/env python3
"""
Checkup (emergency consultation) tests for the Hipocrate API
"""
import aiohttp
import os
import base64

BASE_URL = "http://localhost:44660"
HYP_USER = os.getenv("HYP_USER")
HYP_PASS = os.getenv("HYP_PASS")

def _auth_headers():
    headers = {}
    if HYP_USER and HYP_PASS:
        credentials = base64.b64encode(f"{HYP_USER}:{HYP_PASS}".encode()).decode()
        headers["Authorization"] = f"Basic {credentials}"
    return headers


async def test_checkup_endpoint_missing_id(session: aiohttp.ClientSession) -> bool:
    """GET /api/checkup with no ID should return 404 (route not matched)"""
    print("Testing checkup endpoint with missing ID...")
    try:
        async with session.get(f"{BASE_URL}/api/checkup/", headers=_auth_headers()) as response:
            if response.status in (400, 404):
                print(f"  ✓ /api/checkup/ correctly returned {response.status}")
                return True
            else:
                print(f"  ✗ Expected 400/404, got {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Exception: {e}")
        return False


async def test_checkup_endpoint_known_id(session: aiohttp.ClientSession) -> bool:
    """GET /api/checkup/{id} with a known ID returns expected fields"""
    print("Testing checkup endpoint with known ID...")
    checkup_id = os.getenv("CHECKUP_ID", "421200002270746")
    try:
        async with session.get(f"{BASE_URL}/api/checkup/{checkup_id}", headers=_auth_headers()) as response:
            if response.status != 200:
                print(f"  ✗ Expected 200, got {response.status}")
                return False
            data = await response.json()
            if data.get("status") != "success":
                print(f"  ✗ status={data.get('status')}: {data.get('message')}")
                return False
            for key in ("patient", "checkup"):
                if key not in data:
                    print(f"  ✗ Missing key '{key}' in response")
                    return False
            patient = data["patient"]
            if not patient.get("name"):
                print("  ✗ patient.name is empty")
                return False
            checkup = data["checkup"]
            if not checkup.get("section"):
                print("  ✗ checkup.section is empty")
                return False
            print(f"  ✓ checkup/{checkup_id}: patient={patient.get('name')}, section={checkup.get('section')}")
            return True
    except Exception as e:
        print(f"  ✗ Exception: {e}")
        return False
