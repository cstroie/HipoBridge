#!/usr/bin/env python3
"""
Root endpoint tests for the Hipocrate API
"""
import asyncio
import aiohttp
import os

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
