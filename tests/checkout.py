#!/usr/bin/env python3
"""
Checkout-related tests for the Hipocrate API
"""
import asyncio
import aiohttp
import os

# Configuration
BASE_URL = "http://localhost:44660"
HYP_USER = os.getenv("HYP_USER")
HYP_PASS = os.getenv("HYP_PASS")

async def test_checkout_endpoint_missing_id(session: aiohttp.ClientSession) -> bool:
    """Test checkout endpoint with missing ID"""
    print("Testing checkout endpoint with missing ID...")
    try:
        async with session.get(f"{BASE_URL}/api/checkout") as response:
            if response.status == 400:
                data = await response.json()
                print(f"  ✓ Checkout endpoint with missing ID correctly returned 400: {data.get('message', 'unknown')}")
                return True
            else:
                print(f"  ✗ Checkout endpoint with missing ID should return 400 but got: {response.status}")
                return False
    except Exception as e:
        print(f"  ✗ Checkout endpoint with missing ID test failed with exception: {e}")
        return False
