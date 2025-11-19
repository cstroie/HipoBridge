#!/usr/bin/env python3
"""
Analysis-related tests for the Hipocrate API
"""
import asyncio
import aiohttp
import os

# Configuration
BASE_URL = "http://localhost:44660"
HYP_USER = os.getenv("HYP_USER")
HYP_PASS = os.getenv("HYP_PASS")

async def test_analyses_endpoint_missing_id(session: aiohttp.ClientSession) -> bool:
    """Test analyses endpoint with missing ID"""
    print("Testing analyses endpoint with missing ID...")
    try:
        async with session.get(f"{BASE_URL}/api/analyses") as response:
            if response.status == 400:
                data = await response.json()
                print(f"  ✓ Analyses endpoint with missing ID correctly returned 400: {data.get('message', 'unknown')}")
                return True
            else:
                print(f"  ✗ Analyses endpoint with missing ID should return 400 but got: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Analyses endpoint with missing ID test failed with exception: {e}")
        return False
