#!/usr/bin/env python3
"""
Task (cerere.asp) tests for the Hipocrate API
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


async def test_task_endpoint_missing_id(session: aiohttp.ClientSession) -> bool:
    """GET /fhir/Task with no ID should return 400/404 (route not matched)"""
    print("Testing task (cerere) endpoint with missing ID...")
    try:
        async with session.get(f"{BASE_URL}/fhir/Task/", headers=_auth_headers()) as response:
            if response.status in (400, 404):
                print(f"  ✓ Task with missing ID correctly returned {response.status}")
                return True
            else:
                print(f"  ✗ Task with missing ID should return 400/404 but got: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Task endpoint with missing ID test failed with exception: {e}")
        return False


async def test_task_endpoint_known_id(session: aiohttp.ClientSession) -> bool:
    """GET /fhir/Task/{id} with a known request ID returns expected FHIR fields"""
    print("Testing task (cerere) endpoint with known ID...")
    task_id = os.getenv("TASK_ID", "1743968")
    try:
        async with session.get(f"{BASE_URL}/fhir/Task/{task_id}", headers=_auth_headers()) as response:
            if response.status != 200:
                print(f"  ✗ Expected 200, got {response.status}")
                return False
            data = await response.json()
            if data.get("resourceType") != "Task":
                print(f"  ✗ Expected resourceType=Task, got {data.get('resourceType')}")
                return False
            checks = {
                "status": data.get("status"),
                "focus": data.get("focus"),
                "for": data.get("for"),
            }
            for label, val in checks.items():
                if not val:
                    print(f"  ✗ Missing FHIR field: {label}")
                    return False
            print(f"  ✓ Task/{task_id}: status={data.get('status')}, for={data['for'].get('display')}")
            return True
    except Exception as e:
        print(f"  ✗ Exception: {e}")
        return False
