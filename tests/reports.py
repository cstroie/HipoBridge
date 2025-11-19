#!/usr/bin/env python3
"""
Report-related tests for the Hipocrate API
"""
import asyncio
import aiohttp
import os

# Configuration
BASE_URL = "http://localhost:44660"
HYP_USER = os.getenv("HYP_USER")
HYP_PASS = os.getenv("HYP_PASS")

async def test_report_endpoint_missing_id(session: aiohttp.ClientSession) -> bool:
    """Test report endpoint with missing ID"""
    print("Testing report endpoint with missing ID...")
    try:
        async with session.get(f"{BASE_URL}/api/report") as response:
            if response.status == 400:
                data = await response.json()
                print(f"  ✓ Report endpoint with missing ID correctly returned 400: {data.get('message', 'unknown')}")
                return True
            else:
                print(f"  ✗ Report endpoint with missing ID should return 400 but got: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Report endpoint with missing ID test failed with exception: {e}")
        return False
