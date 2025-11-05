#!/usr/bin/env python3
"""
Test suite for the Hipocrate API
"""
import asyncio
import aiohttp
import os
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:44660"
HYP_USER = os.getenv("HYP_USER")
HYP_PASS = os.getenv("HYP_PASS")

async def test_root_endpoint(session: aiohttp.ClientSession) -> bool:
    """Test the root endpoint"""
    print("Testing root endpoint...")
    try:
        async with session.get(f"{BASE_URL}/") as response:
            if response.status == 200:
                data = await response.json()
                print(f"  ✓ Root endpoint returned: {data}")
                return True
            else:
                print(f"  ✗ Root endpoint failed with status: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Root endpoint failed with exception: {e}")
        return False

async def test_service_get_endpoint(session: aiohttp.ClientSession) -> bool:
    """Test the service GET endpoint"""
    print("Testing service GET endpoint...")
    try:
        async with session.get(f"{BASE_URL}/api/service") as response:
            if response.status == 200:
                data = await response.json()
                print(f"  ✓ Service GET returned status: {data.get('status', 'unknown')}")
                return True
            else:
                print(f"  ✗ Service GET failed with status: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Service GET failed with exception: {e}")
        return False

async def test_service_post_endpoint(session: aiohttp.ClientSession) -> bool:
    """Test the service POST endpoint"""
    print("Testing service POST endpoint...")
    try:
        test_data = {"test": "data"}
        async with session.post(f"{BASE_URL}/api/service", json=test_data) as response:
            if response.status == 200:
                data = await response.json()
                print(f"  ✓ Service POST returned status: {data.get('status', 'unknown')}")
                return True
            else:
                print(f"  ✗ Service POST failed with status: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Service POST failed with exception: {e}")
        return False

async def test_patient_search_endpoint(session: aiohttp.ClientSession) -> bool:
    """Test the patient search endpoint"""
    print("Testing patient search endpoint...")
    try:
        # Test with a simple search term
        async with session.get(f"{BASE_URL}/api/patient/search?term=test") as response:
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

async def test_login_endpoint_success(session: aiohttp.ClientSession) -> bool:
    """Test the login endpoint with valid credentials"""
    print("Testing login endpoint with valid credentials...")
    try:
        # Only run this test if credentials are available
        if not HYP_USER or not HYP_PASS:
            print("  - Skipping login test (no credentials available)")
            return True
            
        login_data = {
            "username": HYP_USER,
            "password": HYP_PASS
        }
        async with session.post(f"{BASE_URL}/api/login", json=login_data) as response:
            if response.status == 200:
                data = await response.json()
                print(f"  ✓ Login endpoint returned: {data.get('message', 'unknown')}")
                return True
            else:
                print(f"  ✗ Login endpoint failed with status: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Login endpoint test failed with exception: {e}")
        return False

async def test_login_endpoint_missing_credentials(session: aiohttp.ClientSession) -> bool:
    """Test the login endpoint with missing credentials"""
    print("Testing login endpoint with missing credentials...")
    try:
        login_data = {
            "username": "testuser"
            # Missing password
        }
        async with session.post(f"{BASE_URL}/api/login", json=login_data) as response:
            if response.status == 400:
                data = await response.json()
                print(f"  ✓ Login with missing credentials correctly returned 400: {data.get('message', 'unknown')}")
                return True
            else:
                print(f"  ✗ Login with missing credentials should return 400 but got: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Login with missing credentials test failed with exception: {e}")
        return False

async def test_login_endpoint_invalid_json(session: aiohttp.ClientSession) -> bool:
    """Test the login endpoint with invalid JSON"""
    print("Testing login endpoint with invalid JSON...")
    try:
        async with session.post(f"{BASE_URL}/api/login", data="invalid json") as response:
            if response.status == 400:
                data = await response.json()
                print(f"  ✓ Login with invalid JSON correctly returned 400: {data.get('message', 'unknown')}")
                return True
            else:
                print(f"  ✗ Login with invalid JSON should return 400 but got: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Login with invalid JSON test failed with exception: {e}")
        return False

async def run_all_tests() -> None:
    """Run all API tests"""
    print(f"Starting API tests against {BASE_URL}")
    print("=" * 50)
    
    async with aiohttp.ClientSession() as session:
        tests = [
            test_root_endpoint,
            test_service_get_endpoint,
            test_service_post_endpoint,
            test_patient_search_endpoint,
            test_invalid_patient_search,
            test_login_endpoint_success,
            test_login_endpoint_missing_credentials,
            test_login_endpoint_invalid_json
        ]
        
        results = []
        for test in tests:
            try:
                result = await test(session)
                results.append(result)
            except Exception as e:
                print(f"Test {test.__name__} failed with exception: {e}")
                results.append(False)
            print()
        
        # Summary
        passed = sum(results)
        total = len(results)
        print("=" * 50)
        print(f"Test Results: {passed}/{total} tests passed")
        
        if passed == total:
            print("All tests passed! 🎉")
        else:
            print(f"{total - passed} tests failed. ❌")

if __name__ == "__main__":
    asyncio.run(run_all_tests())
