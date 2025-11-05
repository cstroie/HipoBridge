#!/usr/bin/env python3
import os
import asyncio
import aiohttp
from aiohttp import web
from typing import Dict, Any, Optional
import json

# Configuration
SERVICE_URL = "http://192.168.3.230/hipocrate"
PORT = 44660

# Get credentials from environment variables
HYP_USER = os.getenv("HYP_USER")
HYP_PASS = os.getenv("HYP_PASS")

# Headers for compatibility with Hipocrate service
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# Global session
session: Optional[aiohttp.ClientSession] = None

async def get_session():
    global session
    if session is None or session.closed:
        session = aiohttp.ClientSession()
    return session

async def root_handler(request):
    return web.json_response({"message": "Web API Interface to Hipocrate Service"})

def is_login_page(content: str) -> bool:
    """Detect if we're on the login page"""
    return "RECUPERARE PAROLA" in content and "Username" in content and "Password" in content

async def login_if_needed() -> bool:
    """Attempt to login if we're on the login page"""
    if not HYP_USER or not HYP_PASS:
        return False
    
    try:
        session = await get_session()
        # Prepare login data
        login_data = {
            "username": HYP_USER,
            "password": HYP_PASS
        }
        
        # Submit login form
        async with session.post(
            SERVICE_URL, 
            data=login_data, 
            headers=HEADERS
        ) as login_response:
            response_text = await login_response.text()
        
        # Check if login was successful (not redirected back to login page)
        if not is_login_page(response_text):
            return True
        return False
    except Exception:
        return False

async def handle_service_request(method: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
    """Handle service requests with automatic login"""
    try:
        session = await get_session()
        # Make initial request
        if method == "GET":
            async with session.get(SERVICE_URL, headers=HEADERS) as response:
                response_text = await response.text()
        else:  # POST
            async with session.post(SERVICE_URL, json=data, headers=HEADERS) as response:
                response_text = await response.text()
        
        # Check if we got redirected to login page
        if is_login_page(response_text):
            # Try to login
            login_success = await login_if_needed()
            if login_success:
                # Retry the original request
                if method == "GET":
                    async with session.get(SERVICE_URL, headers=HEADERS) as response:
                        response_text = await response.text()
                else:  # POST
                    async with session.post(SERVICE_URL, json=data, headers=HEADERS) as response:
                        response_text = await response.text()
                
                # Check if login was successful after retry
                if is_login_page(response_text):
                    return {
                        "status": "error",
                        "message": "Login failed or session expired"
                    }
            else:
                return {
                    "status": "error",
                    "message": "Login required but failed"
                }
        
        return {
            "status": "success",
            "data": response_text
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

async def service_get_handler(request):
    result = await handle_service_request("GET")
    return web.json_response(result)

async def service_post_handler(request):
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({
            "status": "error",
            "message": "Invalid JSON data"
        }, status=400)
    
    result = await handle_service_request("POST", data)
    return web.json_response(result)

async def init_app():
    app = web.Application()
    app.router.add_get('/', root_handler)
    app.router.add_get('/api/service', service_get_handler)
    app.router.add_post('/api/service', service_post_handler)
    
    # Setup startup and cleanup
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    
    return app

async def on_startup(app):
    await get_session()

async def on_cleanup(app):
    global session
    if session and not session.closed:
        await session.close()

if __name__ == "__main__":
    app = init_app()
    web.run_app(app, host="0.0.0.0", port=PORT)
