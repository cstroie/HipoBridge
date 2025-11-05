#!/usr/bin/env python3
import os
import asyncio
import aiohttp
from aiohttp import web
from typing import Dict, Any, Optional
import json
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
SERVICE_URL = "http://192.168.3.230/hipocrate"
PORT = 44660

# Get credentials from environment variables (fallback)
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
        logger.debug("Creating new aiohttp ClientSession with cookie support")
        # Create session with automatic cookie handling
        session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
    else:
        logger.debug("Reusing existing aiohttp ClientSession")
    return session

async def root_handler(request):
    logger.info("Root endpoint accessed")
    return web.json_response({"message": "Web API Interface to Hipocrate Service"})

def is_login_page(content: str) -> bool:
    """Detect if we're on the login page"""
    is_login = "RECUPERARE PAROLA" in content and "Username" in content and "Password" in content
    if is_login:
        logger.debug("Detected login page")
    return is_login

async def login_if_needed(username: str = None, password: str = None) -> bool:
    """Attempt to login if we're on the login page"""
    logger.info("Attempting login if needed")
    
    # Use provided credentials or fallback to environment variables
    user = username or HYP_USER
    pwd = password or HYP_PASS
    
    if not user or not pwd:
        logger.warning("Username or password not set, skipping login")
        return False
    
    try:
        session = await get_session()
        # Prepare login data
        login_data = {
            "username": user,
            "password": pwd
        }
        
        logger.debug(f"Submitting login form to {SERVICE_URL}")
        # Submit login form
        async with session.post(
            SERVICE_URL, 
            data=login_data, 
            headers=HEADERS
        ) as login_response:
            response_text = await login_response.text()
            logger.debug(f"Login response status: {login_response.status}")
            
            # Log cookie information
            if session.cookie_jar:
                cookies = session.cookie_jar.filter_cookies(SERVICE_URL)
                logger.debug(f"Session cookies after login: {len(cookies)} cookies")
        
        # Check if login was successful (not redirected back to login page)
        if not is_login_page(response_text):
            logger.info("Login successful")
            return True
        else:
            logger.warning("Login failed - still on login page")
        return False
    except Exception as e:
        logger.error(f"Login failed with exception: {e}")
        return False

async def handle_service_request(method: str, data: Dict[str, Any] = None, username: str = None, password: str = None) -> Dict[str, Any]:
    """Handle service requests with automatic login"""
    logger.info(f"Handling {method} request to service")
    
    try:
        session = await get_session()
        
        # Log current cookies before request
        if session.cookie_jar:
            cookies = session.cookie_jar.filter_cookies(SERVICE_URL)
            logger.debug(f"Using {len(cookies)} cookies for request")
        
        # Make initial request
        if method == "GET":
            logger.debug(f"Making GET request to {SERVICE_URL}")
            async with session.get(SERVICE_URL, headers=HEADERS) as response:
                response_text = await response.text()
                logger.debug(f"GET response status: {response.status}")
        else:  # POST
            logger.debug(f"Making POST request to {SERVICE_URL} with data: {data}")
            async with session.post(SERVICE_URL, json=data, headers=HEADERS) as response:
                response_text = await response.text()
                logger.debug(f"POST response status: {response.status}")
        
        # Check if we got redirected to login page
        if is_login_page(response_text):
            logger.warning("Detected login page, attempting login")
            # Try to login
            login_success = await login_if_needed(username, password)
            if login_success:
                logger.info("Retrying original request after successful login")
                # Retry the original request
                if method == "GET":
                    async with session.get(SERVICE_URL, headers=HEADERS) as response:
                        response_text = await response.text()
                        logger.debug(f"Retry GET response status: {response.status}")
                else:  # POST
                    async with session.post(SERVICE_URL, json=data, headers=HEADERS) as response:
                        response_text = await response.text()
                        logger.debug(f"Retry POST response status: {response.status}")
                
                # Check if login was successful after retry
                if is_login_page(response_text):
                    logger.error("Login failed or session expired after retry")
                    return {
                        "status": "error",
                        "message": "Login failed or session expired"
                    }
            else:
                logger.error("Login required but failed")
                return {
                    "status": "error",
                    "message": "Login required but failed"
                }
        
        logger.info(f"Service request successful")
        return {
            "status": "success",
            "data": response_text
        }
    except Exception as e:
        logger.error(f"Service request failed with exception: {e}")
        return {
            "status": "error",
            "message": str(e)
        }

async def service_get_handler(request):
    logger.info("GET /api/service endpoint accessed")
    
    # Get credentials from request headers (optional)
    username = request.headers.get("X-Username")
    password = request.headers.get("X-Password")
    
    result = await handle_service_request("GET", username=username, password=password)
    logger.debug(f"GET /api/service response: {result}")
    return web.json_response(result)

async def service_post_handler(request):
    logger.info("POST /api/service endpoint accessed")
    
    # Get credentials from request headers (optional)
    username = request.headers.get("X-Username")
    password = request.headers.get("X-Password")
    
    try:
        data = await request.json()
        logger.debug(f"POST data received: {data}")
    except json.JSONDecodeError:
        logger.error("Invalid JSON data received")
        return web.json_response({
            "status": "error",
            "message": "Invalid JSON data"
        }, status=400)
    
    result = await handle_service_request("POST", data, username=username, password=password)
    logger.debug(f"POST /api/service response: {result}")
    return web.json_response(result)

async def login_handler(request):
    """Explicit login endpoint"""
    logger.info("POST /api/login endpoint accessed")
    
    try:
        # Get credentials from request body
        data = await request.json()
        username = data.get("username")
        password = data.get("password")
        
        if not username or not password:
            logger.warning("Username or password not provided")
            return web.json_response({
                "status": "error",
                "message": "Username and password are required"
            }, status=400)
        
        # Attempt login with provided credentials
        login_success = await login_if_needed(username, password)
        
        if login_success:
            logger.info("Login successful via API endpoint")
            return web.json_response({
                "status": "success",
                "message": "Login successful"
            })
        else:
            logger.error("Login failed via API endpoint")
            return web.json_response({
                "status": "error",
                "message": "Login failed"
            }, status=401)
            
    except json.JSONDecodeError:
        logger.warning("Invalid JSON data received for login")
        return web.json_response({
            "status": "error",
            "message": "Invalid JSON data"
        }, status=400)
    except Exception as e:
        logger.error(f"Login endpoint failed with exception: {e}")
        return web.json_response({
            "status": "error",
            "message": str(e)
        }, status=500)

async def patient_search_handler(request):
    """Search for patients by name or other criteria"""
    logger.info("GET /api/patient/search endpoint accessed")
    
    # Get credentials from request headers (optional)
    username = request.headers.get("X-Username")
    password = request.headers.get("X-Password")
    
    # Get search parameters from query string
    search_term = request.query.get('term', '')
    search_type = request.query.get('type', 'PA')  # PA = patient, P = presentation, etc.
    
    if not search_term:
        logger.warning("No search term provided")
        return web.json_response({
            "status": "error",
            "message": "Search term is required"
        }, status=400)
    
    logger.info(f"Searching for patients with term: {search_term}, type: {search_type}")
    
    try:
        session = await get_session()
        
        # Log current cookies before search
        if session.cookie_jar:
            cookies = session.cookie_jar.filter_cookies(SERVICE_URL)
            logger.debug(f"Using {len(cookies)} cookies for patient search")
        
        # First ensure we're logged in
        login_success = await login_if_needed(username, password)
        if not login_success:
            logger.error("Failed to login for patient search")
            return web.json_response({
                "status": "error",
                "message": "Authentication failed"
            }, status=401)
        
        # Prepare search data
        search_data = {
            "strDescription": search_term,
            "hdnSearchType": "1",  # Simple search
            "searchWhat": search_type,
            "pageNo": "1"
        }
        
        # Make search request to the patient search page
        search_url = f"{SERVICE_URL}/files/search.asp?what={search_type}"
        logger.debug(f"Making patient search request to: {search_url}")
        
        async with session.post(
            search_url,
            data=search_data,
            headers=HEADERS
        ) as response:
            # Handle encoding properly - the service may not be using UTF-8
            try:
                response_text = await response.text()
            except UnicodeDecodeError:
                # If UTF-8 fails, try to get raw bytes and decode with latin-1 or windows-1252
                raw_data = await response.read()
                try:
                    response_text = raw_data.decode('windows-1252')
                except UnicodeDecodeError:
                    response_text = raw_data.decode('latin-1')
            logger.debug(f"Patient search response status: {response.status}")
            
            # Check if we got redirected to login page (session expired)
            if is_login_page(response_text):
                logger.warning("Session expired during patient search, attempting re-login")
                login_success = await login_if_needed(username, password)
                if login_success:
                    # Retry the search
                    async with session.post(
                        search_url,
                        data=search_data,
                        headers=HEADERS
                    ) as retry_response:
                        # Handle encoding properly - the service may not be using UTF-8
                        try:
                            response_text = await retry_response.text()
                        except UnicodeDecodeError:
                            # If UTF-8 fails, try to get raw bytes and decode with latin-1 or windows-1252
                            raw_data = await retry_response.read()
                            try:
                                response_text = raw_data.decode('windows-1252')
                            except UnicodeDecodeError:
                                response_text = raw_data.decode('latin-1')
                        logger.debug(f"Retry search response status: {retry_response.status}")
                        
                        if is_login_page(response_text):
                            logger.error("Login failed after retry")
                            return web.json_response({
                                "status": "error",
                                "message": "Authentication failed after retry"
                            }, status=401)
                else:
                    logger.error("Re-login failed")
                    return web.json_response({
                        "status": "error",
                        "message": "Authentication failed"
                    }, status=401)
            
            logger.info("Patient search completed successfully")
            return web.json_response({
                "status": "success",
                "data": response_text
            })
            
    except Exception as e:
        logger.error(f"Patient search failed with exception: {e}")
        return web.json_response({
            "status": "error",
            "message": str(e)
        }, status=500)

async def init_app():
    logger.info("Initializing web application")
    app = web.Application()
    app.router.add_get('/', root_handler)
    app.router.add_get('/api/service', service_get_handler)
    app.router.add_post('/api/service', service_post_handler)
    app.router.add_get('/api/patient/search', patient_search_handler)
    app.router.add_post('/api/login', login_handler)
    
    # Setup startup and cleanup
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    
    return app

async def on_startup(app):
    logger.info("Application startup")
    await get_session()

async def on_cleanup(app):
    logger.info("Application cleanup")
    global session
    if session and not session.closed:
        logger.debug("Closing aiohttp ClientSession")
        await session.close()

if __name__ == "__main__":
    logger.info(f"Starting web server on port {PORT}")
    app = init_app()
    web.run_app(app, host="0.0.0.0", port=PORT)
