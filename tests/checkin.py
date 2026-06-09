#!/usr/bin/env python3
"""
Checkin (admission record) tests for the Hipocrate API
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


async def test_checkin_endpoint_missing_id(session: aiohttp.ClientSession) -> bool:
    """GET /api/checkin with no ID should return 404 (route not matched)"""
    print("Testing checkin endpoint with missing ID...")
    try:
        async with session.get(f"{BASE_URL}/api/checkin/", headers=_auth_headers()) as response:
            if response.status in (400, 404):
                print(f"  ✓ /api/checkin/ correctly returned {response.status}")
                return True
            else:
                print(f"  ✗ Expected 400/404, got {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Exception: {e}")
        return False


async def test_checkin_endpoint_known_id(session: aiohttp.ClientSession) -> bool:
    """GET /api/checkin/{id} with a known ID returns expected fields"""
    print("Testing checkin endpoint with known ID...")
    checkin_id = os.getenv("CHECKIN_ID", "652001")
    try:
        async with session.get(f"{BASE_URL}/api/checkin/{checkin_id}", headers=_auth_headers()) as response:
            if response.status != 200:
                print(f"  ✗ Expected 200, got {response.status}")
                return False
            data = await response.json()
            if data.get("status") != "success":
                print(f"  ✗ status={data.get('status')}: {data.get('message')}")
                return False
            # Check top-level keys we always expect
            for key in ("patient", "presentation"):
                if key not in data:
                    print(f"  ✗ Missing key '{key}' in response")
                    return False
            patient = data["patient"]
            if not patient.get("name"):
                print("  ✗ patient.name is empty")
                return False
            presentation = data["presentation"]
            if not presentation.get("section"):
                print("  ✗ presentation.section is empty")
                return False
            print(f"  ✓ checkin/{checkin_id}: patient={patient.get('name')}, section={presentation.get('section')}")
            return True
    except Exception as e:
        print(f"  ✗ Exception: {e}")
        return False
