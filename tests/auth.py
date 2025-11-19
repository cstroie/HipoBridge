#!/usr/bin/env python3
"""
Authentication tests for the Hipocrate API
"""
import asyncio
import aiohttp
import os

# Configuration
BASE_URL = "http://localhost:44660"
HYP_USER = os.getenv("HYP_USER")
HYP_PASS = os.getenv("HYP_PASS")

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
