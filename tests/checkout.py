#!/usr/bin/env python3
"""
Encounter-related tests for the Hipocrate API
"""
import asyncio
import aiohttp
import os
import base64

# Configuration
BASE_URL = "http://localhost:44660"
HYP_USER = os.getenv("HYP_USER")
HYP_PASS = os.getenv("HYP_PASS")

def _auth_headers():
    headers = {}
    if HYP_USER and HYP_PASS:
        credentials = base64.b64encode(f"{HYP_USER}:{HYP_PASS}".encode()).decode()
        headers["Authorization"] = f"Basic {credentials}"
    return headers


async def test_encounter_endpoint_missing_id(session: aiohttp.ClientSession) -> bool:
    """Test encounter endpoint with missing ID"""
    print("Testing encounter endpoint with missing ID...")
    try:
        async with session.get(f"{BASE_URL}/fhir/Encounter", headers=_auth_headers()) as response:
            if response.status == 400:
                data = await response.json()
                print(f"  ✓ Encounter endpoint with missing ID correctly returned 400: {data.get('message', 'unknown')}")
                return True
            else:
                print(f"  ✗ Encounter endpoint with missing ID should return 400 but got: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Encounter endpoint with missing ID test failed with exception: {e}")
        return False


async def test_encounter_endpoint_known_id(session: aiohttp.ClientSession) -> bool:
    """GET /fhir/Encounter/{id} with a known ID returns expected FHIR fields"""
    print("Testing encounter endpoint with known ID...")
    encounter_id = os.getenv("CHECKOUT_ID", "260100000619726")
    try:
        async with session.get(f"{BASE_URL}/fhir/Encounter/{encounter_id}", headers=_auth_headers()) as response:
            if response.status != 200:
                print(f"  ✗ Expected 200, got {response.status}")
                return False
            data = await response.json()
            if data.get("resourceType") != "Encounter":
                print(f"  ✗ Expected resourceType=Encounter, got {data.get('resourceType')}")
                return False
            # Check key FHIR fields
            checks = {
                "subject": data.get("subject"),
                "period": data.get("period"),
                "reasonCode or diagnosis": data.get("reasonCode") or data.get("diagnosis"),
            }
            for label, val in checks.items():
                if not val:
                    print(f"  ✗ Missing FHIR field: {label}")
                    return False
            # Check new fields added in v5
            has_fo = any(
                i.get("type", {}).get("coding", [{}])[0].get("code") == "FO"
                for i in (data.get("identifier") or [])
            )
            print(f"  ✓ Encounter/{encounter_id}: period={data['period']}, FO identifier={'yes' if has_fo else 'no'}")
            return True
    except Exception as e:
        print(f"  ✗ Exception: {e}")
        return False
