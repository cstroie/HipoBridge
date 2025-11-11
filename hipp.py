#!/usr/bin/env python3
"""
HippoBridge - FHIR Bridge for Hipocrate Medical System

This application provides a FHIR-compatible API bridge to access patient data 
from the Hipocrate medical system. It exposes endpoints for patient search, 
retrieval, observations, diagnostic reports, and encounters.

Key Features:
- FHIR-compatible REST API
- Patient search by name, CNP, or patient code
- Patient data retrieval with checkin/checkout IDs
- Observation (analysis) listing and details
- Diagnostic report retrieval with redirect handling
- Encounter (checkout) information
- CNP validation and parsing
- Web interface for patient analysis
- Configuration via file with environment variable overrides

Configuration:
- Server settings (host, port) in hipp.cfg
- Hipocrate service URL in hipp.cfg
- Credentials via HYP_USER and HYP_PASS environment variables
- Local overrides in local.cfg (optional)

Author: Costin Stroie <costinstroie@eridu.eu.org>
License: GPL-3.0
Version: 1.0.0
"""
import os
import asyncio
import aiohttp
from aiohttp import web
from yarl import URL
from typing import Dict, Any, Optional, List
import json
import logging
import re
from bs4 import BeautifulSoup
import html
from datetime import datetime
import configparser


# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)8s | %(message)s'
)
logger = logging.getLogger('HippoBridge')

# Default configuration
DEFAULT_CONFIG = {
    'server': {
        'port': '44660',
        'host': '0.0.0.0'
    },
    'hipocrate': {
        'service_url': 'http://127.0.0.1/hipocrate'
    }
}

def load_config():
    """Load configuration from hipp.cfg and local.cfg (if exists).
    
    Returns:
        dict: Configuration dictionary with merged settings
    """
    config = configparser.ConfigParser()
    
    # Read default config
    config.read_dict(DEFAULT_CONFIG)
    
    # Load main config file
    if os.path.exists('hipp.cfg'):
        logger.info("Loading hipp.cfg configuration")
        config.read('hipp.cfg')
    else:
        logger.info("hipp.cfg not found, using default configuration")
    
    # Load local config if exists (will override hipp.cfg)
    if os.path.exists('local.cfg'):
        logger.info("Loading local.cfg configuration (overrides hipp.cfg)")
        config.read('local.cfg')
    
    return config

# Load configuration
config = load_config()

# Configuration values
SERVICE_URL = config.get('hipocrate', 'service_url')
PORT = config.getint('server', 'port')
HOST = config.get('server', 'host')

# Get credentials from environment variables (fallback)
HYP_USER = os.getenv("HYP_USER")
HYP_PASS = os.getenv("HYP_PASS")

# Headers for compatibility with Hipocrate service
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ro-RO,ro;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# Analysis types dictionary for reuse across functions
ANALYSIS_TYPES = {
    "radio": {
        "display": "Radiology",
        "definition": "Radiology"
    },
    "ct": {
        "display": "CT Scan",
        "definition": "Computed Tomography"
    },
    "irm": {
        "display": "MRI",
        "definition": "Magnetic Resonance Imaging"
    },
    "eco": {
        "display": "Ultrasound",
        "definition": "Echography"
    },
    "lab": {
        "display": "Laboratory",
        "definition": "Laboratory tests"
    },
    "lac": {
        "display": "Angiography and Cardiac Catheterization",
        "definition": "Angiography and Cardiac Catheterization"
    },
    "lii": {
        "display": "Interventional Radiology",
        "definition": "Interventional Radiology"
    },
    "rads": {
        "display": "Fluoroscopy and CEUS",
        "definition": "Fluoroscopy and Contrast-Enhanced Ultrasound"
    },
    "apa": {
        "display": "Anatomopathology",
        "definition": "Anatomopathology"
    }
}

# Global session
session: Optional[aiohttp.ClientSession] = None

# Simple in-memory cache for CNP to patient code mappings
cnp_cache: Dict[str, str] = {}
cache_max_size = 1000  # Maximum number of entries to cache

def create_error_response(message: str, status_code: int = 400, details: Dict[str, Any] = None) -> web.Response:
    """Create a standardized error response.
    
    Args:
        message: Error message
        status_code: HTTP status code (default: 400)
        details: Additional error details
        
    Returns:
        Standardized JSON error response
    """
    response_data = {
        "status": "error",
        "message": message
    }
    
    if details:
        response_data["details"] = details
    
    return web.json_response(response_data, status=status_code)

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
    """Handle requests to the root endpoint.
    
    Returns a web page with a CNP input form and analysis functionality.
    
    Args:
        request: The incoming HTTP request
        
    Returns:
        HTML response with the web interface
    """
    logger.info("Root endpoint accessed")
    
    # Serve the external HTML file
    with open('static/main.html', 'r') as f:
        html_content = f.read()
    
    return web.Response(text=html_content, content_type='text/html')

def is_login_page(content: str) -> bool:
    """Detect if the provided content is a login page.
    
    Checks for 'Identificare' in the HTML title to determine if we're on the login page.
    
    Args:
        content: HTML content to check
        
    Returns:
        True if content appears to be a login page, False otherwise
    """
    # Parse the HTML content to extract the title
    try:
        soup = BeautifulSoup(content, 'html.parser')
        title = soup.find('title')
        is_login = title and 'Identificare' in title.get_text()
    except Exception:
        # Fallback to simple string check if parsing fails
        is_login = "Username" in content and "Password" in content
    # Log detection result
    if is_login:
        logger.debug("Detected login page")
    return is_login

async def login_if_needed(username: str = None, password: str = None) -> bool:
    """Attempt to login to the Hipocrate service if needed.
    
    Checks if we're currently on the login page, and if so, performs login
    using the provided or environment credentials.
    
    Args:
        username: Username for login. Defaults to environment variable.
        password: Password for login. Defaults to environment variable.
        
    Returns:
        True if login was successful or not needed, False otherwise
    """
    logger.info("Attempting login if needed")
    
    # Use provided credentials or fallback to environment variables
    user = username or HYP_USER
    pwd = password or HYP_PASS
    
    if not user or not pwd:
        logger.warning("Username or password not set, skipping login")
        return False
    
    try:
        session = await get_session()
        
        # First, check if we're already logged in by accessing main.asp
        main_url = f"{SERVICE_URL}/main.asp"
        logger.debug(f"Checking if already logged in by accessing: {main_url}")
        async with session.get(main_url, headers=HEADERS) as main_response:
            # Handle encoding properly - the service may not be using UTF-8
            try:
                main_text = await main_response.text()
            except UnicodeDecodeError:
                # If UTF-8 fails, try to get raw bytes and decode with latin-1 or windows-1252
                raw_data = await main_response.read()
                try:
                    main_text = raw_data.decode('windows-1252')
                except UnicodeDecodeError:
                    main_text = raw_data.decode('latin-1')
            logger.debug(f"Main page response status: {main_response.status}")
            
            # If we're not on the login page, we're already logged in
            if not is_login_page(main_text):
                logger.info("Already logged in, skipping login")
                return True
        
        # If we're on the login page, proceed with login
        logger.info("Not logged in, proceeding with login")
        
        # First, access the default.asp page to get initial cookies
        default_url = f"{SERVICE_URL}/default.asp"
        logger.debug(f"Accessing default page to get cookies: {default_url}")
        async with session.get(default_url, headers=HEADERS) as default_response:
            logger.debug(f"Default page response status: {default_response.status}")
            
        # Prepare login data to match browser submission
        login_data = {
            "id_recuperare_pwd_2": "",
            "strUser": user,
            "strPwd": pwd,
            "cboLang": "ro"
        }
        
        # Add referer header for the login request
        login_headers = HEADERS.copy()
        login_headers["Referer"] = default_url
        
        # Use the correct login endpoint
        login_url = f"{SERVICE_URL}/security/logon.asp"
        logger.debug(f"Submitting login form to {login_url}")
        # Submit login form
        async with session.post(
            login_url, 
            data=login_data, 
            headers=login_headers
        ) as login_response:
            response_text = await login_response.text()
            logger.debug(f"Login response status: {login_response.status}")
            
            # Log cookie information
            if session.cookie_jar:
                cookies = session.cookie_jar.filter_cookies(URL(SERVICE_URL))
                logger.debug(f"Session cookies after login: {len(cookies)} cookies")
        
        # Check if login was successful (redirect to main.asp or not on login page)
        if login_response.status == 302 and "main.asp" in login_response.headers.get("Location", ""):
            logger.info("Login successful: redirected to main.asp")
            return True
        elif not is_login_page(response_text):
            logger.info("Login successful: not on login page")
            return True
        else:
            logger.warning("Login failed: still on login page")
        return False
    except Exception as e:
        logger.error(f"Login failed with exception: {e}")
        return False


async def fhir_login(request):
    """Handle explicit login requests.
    
    Performs login to the Hipocrate service using credentials provided in the request body.
    
    Args:
        request: The incoming HTTP request with JSON body containing username and password
        
    Returns:
        JSON response indicating login success or failure
    """
    logger.info("POST /fhir/login endpoint accessed")
    
    try:
        # Get credentials from request body
        data = await request.json()
        username = data.get("username")
        password = data.get("password")
        
        if not username or not password:
            logger.warning("Username or password not provided")
            return create_error_response("Username and password are required")
        
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
            return create_error_response("Login failed", 401)
            
    except json.JSONDecodeError:
        logger.warning("Invalid JSON data received for login")
        return create_error_response("Invalid JSON data")
    except Exception as e:
        logger.error(f"Login endpoint failed with exception: {e}")
        return create_error_response(str(e), 500)

async def make_authenticated_request(session, url, method="GET", data=None, username=None, password=None):
    """Make an authenticated request to the Hipocrate service with automatic login handling.
    
    Args:
        session: The aiohttp session to use
        url: The URL to request
        method: HTTP method ("GET" or "POST")
        data: Data to send with POST requests
        username: Username for login if needed
        password: Password for login if needed
        
    Returns:
        Tuple of (response_text, success, error_response) where success is boolean
    """
    
    async def _make_request(use_retry_headers=False):
        """Helper function to make a request with proper headers."""
        if method == "GET":
            logger.debug(f"Making GET request to: {url}")
            async with session.get(url, headers=HEADERS) as response:
                response_text = await handle_response_encoding(response)
                logger.debug(f"GET response status: {response.status}")
        else:  # POST
            logger.debug(f"Making POST request to: {url}")
            # For POST requests, we need to be careful about Content-Type headers
            # Create a copy of headers without Content-Type to avoid conflicts
            post_headers = HEADERS.copy()
            if use_retry_headers or method == "POST":
                post_headers.pop("Content-Type", None)
            # When sending form data, let aiohttp set the Content-Type automatically
            if data:
                async with session.post(url, data=data, headers=post_headers) as response:
                    response_text = await handle_response_encoding(response)
                    logger.debug(f"POST response status: {response.status}")
            else:
                async with session.post(url, headers=post_headers) as response:
                    response_text = await handle_response_encoding(response)
                    logger.debug(f"POST response status: {response.status}")
        return response_text
    
    try:
        # Log current cookies before request
        if session.cookie_jar:
            cookies = session.cookie_jar.filter_cookies(URL(SERVICE_URL))
            logger.debug(f"Using {len(cookies)} cookies for request to {url}")
        
        # Make the initial request
        response_text = await _make_request()
        
        # Check if we got redirected to login page (session expired)
        if is_login_page(response_text):
            logger.warning(f"Session expired during request to {url}, attempting re-login")
            login_success = await login_if_needed(username, password)
            if login_success:
                # Retry the request with special headers for POST
                response_text = await _make_request(use_retry_headers=True)
                # Check again if still on login page
                if is_login_page(response_text):
                    logger.error("Login failed after retry")
                    return None, False, create_error_response("Authentication failed after retry", 401)
            else:
                logger.error("Re-login failed")
                return None, False, create_error_response("Authentication failed", 401)
        # If we reach here, we have a valid response
        return response_text, True, None
    except Exception as e:
        logger.error(f"Request to {url} failed with exception: {e}")
        return None, False, create_error_response(str(e), 500)

async def handle_response_encoding(response):
    """Handle response encoding for the Hipocrate service.
    
    Args:
        response: The aiohttp response object
        
    Returns:
        Decoded response text
    """
    try:
        response_text = await response.text()
    except UnicodeDecodeError:
        # If UTF-8 fails, try to get raw bytes and decode with latin-1 or windows-1252
        raw_data = await response.read()
        try:
            response_text = raw_data.decode('windows-1252')
        except UnicodeDecodeError:
            response_text = raw_data.decode('latin-1')
    return response_text

async def fhir_patient_search(request):
    """Search for patients by name or other criteria.
    
    Performs a patient search on the Hipocrate service using the provided search term.
    Can return either a single patient result or multiple patient results.
    If the search term ends with *, it's treated as a partial CNP search.
    
    Args:
        request: The incoming HTTP request with 'q' query parameter for search term
                 and optional X-Username and X-Password headers for authentication
        
    Returns:
        JSON response with search results or error information
    """
    logger.info("GET /fhir/Patient endpoint accessed")
    
    # Get credentials from request headers (optional)
    username = request.headers.get("X-Username")
    password = request.headers.get("X-Password")
    
    # Get search parameter from query string
    search_term = request.query.get('q', '')
    
    if not search_term:
        logger.warning("No search term provided")
        return create_error_response("Search term is required")
    
    try:
        session = await get_session()
        
        # Determine search type based on input
        search_type = "name"  # default
        actual_search_term = search_term
        cnp_value = ""
        
        # Check if search term is numeric
        if search_term.isdigit():
            # If it's 13 digits, validate as CNP
            if len(search_term) == 13:
                if validate_cnp(search_term):
                    search_type = "cnp"
                    cnp_value = search_term
                    logger.info(f"Performing CNP search for: {search_term}")
                else:
                    # Not a valid CNP, treat as patient code
                    search_type = "code"
                    logger.info(f"Performing patient code search for: {search_term}")
            else:
                # Numeric but not 13 digits, treat as patient code
                search_type = "code"
                logger.info(f"Performing patient code search for: {search_term}")
        else:
            # Check if search term ends with *, treat as partial CNP
            if search_term.endswith('*'):
                # Validate that the part before * is all digits
                prefix = search_term[:-1]
                if prefix.isdigit() and len(prefix) < 13:
                    search_type = "partial_cnp"
                    actual_search_term = search_term  # Keep the asterisk for Hipocrate
                    cnp_value = prefix
                    logger.info(f"Performing partial CNP search for: {search_term}")
                else:
                    # Not a valid partial CNP, treat as name search
                    search_type = "name"
                    actual_search_term = search_term
                    logger.info(f"Searching for patients by name: {search_term}")
            else:
                # Not numeric, treat as name search
                search_type = "name"
                actual_search_term = search_term
                logger.info(f"Searching for patients by name: {search_term}")
        
        # Prepare full search data as captured in the POST request
        search_data = {
            "hdnSearchType": "1",
            "pageNo": "1",
            "strDescription": actual_search_term if search_type in ["name", "code", "cnp", "partial_cnp"] else "",
            "strLastName": "",
            "strFirstName": "",
            "strCodePres": "",
            "strCNP": "",
            "strSDate": "",
            "strEDate": "",
            "strProfessionID": "",
            "strSex": "",
            "strReference": "",
            "selSection": "0",
            "selDoctor": "",
            "intDiagnosisP": "",
            "DiagnosisP": "",
            "intDiagnosisPDRG": "",
            "DiagnosisPDRG": "",
            "searchWhat": "PA",
            "strShowLastFile": "1",
            "strCheckedIn": "-1",
            "strCODQR": "",
            "btnCODQR": "IMPORTA COD QR",
            "btnCODQRClear": "STERGE COD QR",
            "hdnQRSave": "",
            "IdQR": ""
        }
        
        # Make search request to the patient search page
        search_url = f"{SERVICE_URL}/files/search.asp?what=PA"
        
        # For POST requests, we need to be careful about Content-Type headers
        # Create a copy of headers without Content-Type to avoid conflicts
        post_headers = HEADERS.copy()
        post_headers.pop("Content-Type", None)  # Remove Content-Type if present
        
        response_text, success, error_response = await make_authenticated_request(
            session, search_url, "POST", search_data, username, password
        )
        
        if not success:
            return error_response
        
        logger.info("Patient search completed successfully")
        
        # Try to parse as single patient page first
        patient_data = parse_patient_data(response_text)
        if patient_data and patient_data.get("patient_name") and not patient_data.get("error"):
            fhir_patient = convert_to_fhir_patient(patient_data, request)
            return web.json_response(fhir_patient)
        
        # Try to parse as multiple patients page
        multiple_patients_data = parse_multiple_patients_data(response_text)
        if multiple_patients_data and len(multiple_patients_data) > 0:
            # Convert multiple patients to FHIR Bundle
            bundle = {
                "resourceType": "Bundle",
                "type": "searchset",
                "total": len(multiple_patients_data),
                "entry": []
            }
            
            for patient in multiple_patients_data:
                # Create minimal FHIR patient resource for each
                name_parts = patient.get("patient_name", "").split()
                family_name = name_parts[0] if len(name_parts) > 0 else ""
                given_names = name_parts[1:] if len(name_parts) > 1 else []
                
                fhir_patient = {
                    "resourceType": "Patient",
                    "id": patient.get("patient_id", ""),
                    "identifier": [
                        {
                            "system": f"http://{request.host}/fhir/NamingSystem/patient-id",
                            "value": patient.get("patient_id", "")
                        }
                    ],
                    "name": [
                        {
                            "use": "official",
                            "family": family_name,
                            "given": given_names
                        }
                    ]
                }
                
                # Add CNP if available
                if patient.get("patient_cnp"):
                    fhir_patient["identifier"].append({
                        "system": f"http://{request.host}/fhir/NamingSystem/cnp",
                        "value": patient.get("patient_cnp", "")
                    })
                
                bundle["entry"].append({
                    "resource": fhir_patient
                })
            
            return web.json_response(bundle)
        
        # Check if we're on a "no results" page
        if "nu a fost gasit" in response_text.lower() or "no results" in response_text.lower():
            # Return empty FHIR Bundle
            bundle = {
                "resourceType": "Bundle",
                "type": "searchset",
                "total": 0,
                "entry": []
            }
            return web.json_response(bundle)
        
        # If we have patient data with an error, return that error
        if patient_data and patient_data.get("error"):
            logger.warning(f"Patient data parsing error: {patient_data['error']}")
            return create_error_response(patient_data["error"], 404)
        
        # If neither parser worked, return an error
        logger.warning("Unable to parse patient search results")
        logger.debug(f"Response text snippet: {response_text[:500]}...")  # Log snippet for debugging
        return create_error_response(
            "Unable to parse patient search results", 
            500, 
            {"type": "parse_error"}
        )
            
    except Exception as e:
        logger.error(f"Patient search failed with exception: {e}")
        return create_error_response(str(e), 500)

def html_to_markdown(html_content: str) -> str:
    """Convert HTML content to clean markdown text.
    
    Processes HTML content by removing unnecessary tags, converting formatting
    elements to markdown syntax, and normalizing whitespace.
    
    Args:
        html_content: HTML content to convert
        
    Returns:
        Clean markdown text
    """
    
    try:
        # First convert HTML entities to their characters
        html_content = html.unescape(html_content)
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove XML namespace declarations and processing instructions
        for ns_decl in soup.find_all(re.compile(r'^\?xml')):
            ns_decl.decompose()
        
        # Remove Microsoft Office specific tags
        for tag in soup.find_all(['o:p', 'xml:namespace']):
            tag.decompose()
        
        # Remove wrapping <b> tags that might enclose the entire content
        # Check if there's a single <b> tag that contains everything
        body_content = soup.find('body')
        if body_content:
            content_children = list(body_content.children)
            if len(content_children) == 1 and content_children[0].name == 'b':
                # If the only child is a <b> tag, unwrap it
                content_children[0].unwrap()
        else:
            # If no body tag, check if the soup itself has a single <b> child
            root_children = list(soup.children)
            # Filter out text nodes that are only whitespace
            element_children = [child for child in root_children if hasattr(child, 'name') and child.name]
            if len(element_children) == 1 and element_children[0].name == 'b':
                # If the only element child is a <b> tag, unwrap it
                element_children[0].unwrap()
        
        # Convert common HTML elements to markdown
        # Headings
        for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            level = int(tag.name[1])
            tag.insert_before('#' * level + ' ')
            tag.insert_after('\n\n')
            tag.unwrap()
        
        # Paragraphs
        for p in soup.find_all('p'):
            p.insert_after('\n\n')
            p.unwrap()
        
        # Line breaks
        for br in soup.find_all('br'):
            br.replace_with('\n')
        
        # Bold (but skip if it's a wrapper tag)
        for b in soup.find_all(['b', 'strong']):
            # Check if this is a wrapper tag (contains all other content)
            parent_children = list(b.parent.children)
            # Filter out text nodes that are only whitespace
            element_children = [child for child in parent_children if hasattr(child, 'name') and child.name]
            
            # Skip if this is a wrapper tag (only child element in parent)
            is_wrapper = (b.parent.name == 'body' or b.parent == soup) and len(element_children) == 1
            if not is_wrapper:
                b.insert_before('**')
                b.insert_after('**')
            b.unwrap()
        
        # Italic
        for i in soup.find_all(['i', 'em']):
            i.insert_before('*')
            i.insert_after('*')
            i.unwrap()
        
        # Underline (convert to italic as markdown doesn't have underline)
        for u in soup.find_all('u'):
            u.insert_before('*')
            u.insert_after('*')
            u.unwrap()
        
        # Remove excessive whitespace and HTML entities
        text = soup.get_text()
        # Decode HTML entities
        text = html.unescape(text)
        # Remove various forms of non-breaking spaces
        text = text.replace('\xa0', ' ')  # &nbsp; character entity
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;nbsp;', ' ')
        # Normalize whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = text.strip()
        
        return text
    except Exception as e:
        # If parsing fails, return cleaned text
        # Decode HTML entities
        cleaned_text = html.unescape(html_content)
        # Remove various forms of non-breaking spaces
        cleaned_text = cleaned_text.replace('\xa0', ' ')  # &nbsp; character entity
        cleaned_text = cleaned_text.replace('&nbsp;', ' ')
        cleaned_text = cleaned_text.replace('&amp;nbsp;', ' ')
        return re.sub(r'\s+', ' ', cleaned_text.strip())

def get_textarea_content_after_label(soup: 'BeautifulSoup', label_regex: str) -> str:
    """Get content of first textarea after a label matching the given regex.
    
    Searches for a label matching the regex pattern and returns the content
    of the first textarea element that follows it.
    
    Args:
        soup: Parsed HTML content
        label_regex: Regular expression pattern to match label text
        
    Returns:
        Content of the textarea converted to markdown, or empty string if not found
    """
    import re
    
    try:
        # Find elements with text matching the label regex
        label_elements = soup.find_all(string=re.compile(label_regex, re.IGNORECASE))
        if label_elements:
            # Get the parent element which should contain the label
            parent = label_elements[0].parent
            if parent:
                # Find the next textarea sibling
                textarea = parent.find_next('textarea')
                if textarea:
                    return html_to_markdown(str(textarea))
        return ""
    except Exception as e:
        logger.error(f"Error extracting textarea content after label '{label_regex}': {e}")
        return ""

def parse_report_data(html_content: str) -> Dict[str, Any]:
    """Parse HTML report content and extract structured data.
    
    Extracts patient information, examination details, and report results
    from HTML report content.
    
    Args:
        html_content: HTML content of the report
        
    Returns:
        Dictionary containing parsed report data
    """
    
    try:
        # First convert HTML entities to their characters
        html_content = html.unescape(html_content)
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Initialize result dictionary
        report_data = {
            "patient_name": "",
            "age": "",
            "gender": "",
            "patient_cnp": "",
            "patient_id": "",
            "sample_datetime": "",
            "sample_date": "",
            "sample_time": "",
            "examination": "",
            "reports": [],  # List of reports instead of single result
            "examiner": ""
        }
        
        # Extract text content for pattern matching
        text_content = soup.get_text()
        
        # Extract patient name
        name_match = re.search(r'(?:Nume:|PACIENT:)\s*([^\n\r<>&]+?)(?:\s+VARSTA:|\s+SEX:|\s+C\.N\.P:|\s+COD\s+PACIENT:)', text_content, re.IGNORECASE)
        if name_match:
            report_data["patient_name"] = re.sub(r'\s+', ' ', name_match.group(1).strip())
        else:
            # Fallback pattern if the above doesn't match
            name_match = re.search(r'(?:Nume:|PACIENT:)\s*([^\n\r<>&]+)', text_content, re.IGNORECASE)
            if name_match:
                report_data["patient_name"] = re.sub(r'\s+', ' ', name_match.group(1).strip())
        
        # Extract age
        age_match = re.search(r'Varsta:\s*([^\n\r<>&]+)', text_content, re.IGNORECASE)
        if age_match:
            report_data["age"] = re.sub(r'\s+', ' ', age_match.group(1).strip())
        
        # Extract gender
        gender_match = re.search(r'Sex:\s*([^\n\r<>&]+)', text_content, re.IGNORECASE)
        if gender_match:
            report_data["gender"] = re.sub(r'\s+', ' ', gender_match.group(1).strip())
        
        # Extract patient CNP
        cnp_match = re.search(r'C\.N\.P:\s*([^\n\r<>&]+)', text_content, re.IGNORECASE)
        if cnp_match:
            report_data["patient_cnp"] = re.sub(r'\s+', ' ', cnp_match.group(1).strip())
        
        # Extract patient code
        code_match = re.search(r'Cod pacient:\s*([^\n\r<>&]+)', text_content, re.IGNORECASE)
        if code_match:
            report_data["patient_id"] = re.sub(r'\s+', ' ', code_match.group(1).strip())
        
        # Extract sample date and time
        datetime_match = re.search(r'(?:Data si ora recoltarii:|Data investigatiei:)\s*([^\n\r<>&]+)', text_content, re.IGNORECASE)
        if datetime_match:
            datetime_str = re.sub(r'\s+', ' ', datetime_match.group(1).strip())
            report_data["sample_datetime"] = datetime_str
            
            # Try to parse date and time
            try:
                # Handle common date formats
                if re.match(r'\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}', datetime_str):
                    dt = datetime.strptime(datetime_str, '%d/%m/%Y %H:%M:%S')
                    report_data["sample_date"] = dt.strftime('%Y-%m-%d')
                    report_data["sample_time"] = dt.strftime('%H:%M:%S')
                elif re.match(r'\d{2}/\d{2}/\d{4}', datetime_str):
                    dt = datetime.strptime(datetime_str, '%d/%m/%Y')
                    report_data["sample_date"] = dt.strftime('%Y-%m-%d')
            except ValueError:
                # If parsing fails, leave date/time fields empty
                pass
        
        # Extract examination
        exam_match = re.search(r'EXAMINARE EFECTUATA:\s*([^\n\r<>&]+)', text_content, re.IGNORECASE)
        if exam_match:
            report_data["examination"] = re.sub(r'\s+', ' ', exam_match.group(1).strip())
        
        # Extract multiple reports
        # Find all elements with text starting with "REZULTAT:"
        result_elements = soup.find_all(string=re.compile(r'^REZULTAT:', re.IGNORECASE))
        
        for result_element in result_elements:
            try:
                # The investigation name is the text after "REZULTAT:" in the element
                element_text = result_element.get_text()
                investigation_match = re.search(r'REZULTAT:\s*(.*?)(?:\s*$)', element_text, re.IGNORECASE)
                investigation_name = ""
                if investigation_match:
                    investigation_name = investigation_match.group(1).strip()
                
                # Find the next div sibling which contains the actual result
                result_div = result_element.find_next('div')
                result_content = ""
                if result_div:
                    # Check if the div contains only a single <b> tag as its child
                    div_children = list(result_div.children)
                    # Filter out text nodes that contain only whitespace
                    element_children = [child for child in div_children if hasattr(child, 'name') and child.name]
                    
                    if len(element_children) == 1 and element_children[0].name == 'b':
                        # If the only child is a <b> tag, use its content directly
                        result_content = html_to_markdown(str(element_children[0]))
                    else:
                        # Otherwise, process the entire div
                        result_content = html_to_markdown(str(result_div))
                
                # Add to reports list
                report_data["reports"].append({
                    "investigation": investigation_name,
                    "result": result_content
                })
            except Exception as e:
                logger.error(f"Error parsing individual report: {e}")
                continue
        
        # Extract examiner (MEDIC, or Medic validator:)
        # Handle both plain text and HTML formatted examiner names
        examiner_patterns = [
            r'(?:MEDIC,|Medic validator:)\s*([^\n\r<>&]+)',
            r'(?:MEDIC,|Medic validator:)\s*<b[^>]*>([^<]+)</b>',
            r'(?:MEDIC,|Medic validator:)[^>]*>\s*([^\n\r<>&]+)'
        ]
        
        examiner_name = ""
        for pattern in examiner_patterns:
            examiner_match = re.search(pattern, html_content, re.IGNORECASE)
            if examiner_match:
                examiner_name = examiner_match.group(1).strip()
                # Clean up HTML entities and extra whitespace
                examiner_name = html.unescape(examiner_name)
                examiner_name = re.sub(r'\s+', ' ', examiner_name)
                break
        
        if examiner_name:
            report_data["examiner"] = examiner_name
        
        return report_data
    except Exception as e:
        logger.error(f"Error parsing report data: {e}")
        return {}

def is_expected_page(soup: BeautifulSoup, expected_title_text: str) -> bool:
    """Check if the parsed HTML content is the expected page by looking for specific text in the title.
    
    Args:
        soup: BeautifulSoup object of the parsed HTML content
        expected_title_text: Text that should be present in the page title
        
    Returns:
        True if the page title contains the expected text, False otherwise
    """
    title = soup.find('title')
    return title and expected_title_text in title.get_text()

def parse_patient_data(html_content: str) -> Dict[str, Any]:
    """Parse HTML content for a single patient page and extract patient data.
    
    Extracts patient name, CNP, id, and associated encounter/admission/discharge IDs
    from a single patient page HTML content.
    
    Args:
        html_content: HTML content of the single patient page
        
    Returns:
        Dictionary containing parsed patient data, or empty dict if not a patient page
        Returns {"error": "Invalid patient id"} if patient name is empty
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Check if this is a single patient page by looking for 'Date pasaportale' in title
        if not is_expected_page(soup, 'Date pasaportale'):
            return {"error": "Backend returned an unexpected page"}
        
        # Check if there is patient data on page by getting the name from the div with id "div_navbar"
        navbar_div = soup.find('div', id='div_navbar')
        if not navbar_div:
            logger.warning("No navbar div found, invalid patient id")
            return {"error": "Invalid patient id"}
        
        patient_name_from_navbar = navbar_div.get_text().strip()
        if not patient_name_from_navbar:
            logger.warning("Patient name from navbar is empty, invalid patient id")
            return {"error": "Invalid patient id"}
        
        # Patient data
        patient_data = {
            "encounters": [],
            "admissions": [],
            "discharges": []
        }
        
        # Extract patient name from input elements
        family_input = soup.find('input', id='strNume', type='text')
        if family_input:
            patient_data["family_name"] = family_input.get('value', '').strip()
        
        given_input = soup.find('input', id='strPrenume', type='text')
        if given_input:
            patient_data["given_name"] = given_input.get('value', '').strip()
        
        patient_name = f"{patient_data.get('family_name', '')} {patient_data.get('given_name', '')}".strip()
        
        # If patient name is empty or null, the patient id is invalid
        if not patient_name:
            logger.warning("Patient name is empty, invalid patient id")
            return {"error": "Invalid patient id"}
        
        # Extract patient ID (CNP) from input element with id "strCNP"
        cnp_input = soup.find('input', id='strCNP', type='text')
        if cnp_input:
            patient_data["patient_cnp"] = cnp_input.get('value', '').strip()
        
        # Extract patient id from hidden input with id "hdnCodeID"
        id_input = soup.find('input', id='hdnCodeID', type='hidden')
        if id_input:
            patient_data["patient_id"] = id_input.get('value', '').strip()
        
        # Extract CID
        cid_input = soup.find('input', id='strCID', type='text')
        if cid_input:
            patient_data["cid"] = cid_input.get('value', '').strip()
        
        # Extract phone
        phone_input = soup.find('input', id='strTelefon', type='text')
        if phone_input:
            patient_data["phone"] = phone_input.get('value', '').strip()
        
        # Extract email
        email_input = soup.find('input', id='strEmail', type='text')
        if email_input:
            patient_data["email"] = email_input.get('value', '').strip()
        
        # Extract weight
        weight_input = soup.find('input', id='strGreutate', type='text')
        if weight_input:
            patient_data["weight"] = weight_input.get('value', '').strip()
        
        # Extract height
        height_input = soup.find('input', id='strInaltime', type='text')
        if height_input:
            patient_data["height"] = height_input.get('value', '').strip()
        
        # Extract MCP
        mcp_input = soup.find('input', id='strmcp', type='text')
        if mcp_input:
            patient_data["mcp"] = mcp_input.get('value', '').strip()
        
        # Extract address from SELECT with id strDomLegal_LocId
        address_select = soup.find('select', id='strDomLegal_LocId')
        if address_select:
            selected_option = address_select.find('option', selected=True)
            if selected_option:
                patient_data["address"] = selected_option.get_text().strip()
        
        # Derive sex and birth date from CNP if available
        if patient_data.get("patient_cnp"):
            parsed_cnp = parse_cnp(patient_data["patient_cnp"])
            if parsed_cnp.get("valid"):
                patient_data["sex"] = parsed_cnp.get("gender", "unknown")
                patient_data["birth_date"] = parsed_cnp.get("birth_date", "")
        
        # If we couldn't derive birth date from CNP, try to get it from strDataNastere input
        if not patient_data.get("birth_date"):
            birth_date_input = soup.find('input', id='strDataNastere', type='text')
            if birth_date_input:
                birth_date_value = birth_date_input.get('value', '').strip()
                # Convert DD/MM/YYYY format to YYYY-MM-DD
                if birth_date_value and re.match(r'\d{2}/\d{2}/\d{4}', birth_date_value):
                    try:
                        day, month, year = birth_date_value.split('/')
                        patient_data["birth_date"] = f"{year}-{month}-{day}"
                    except Exception:
                        pass  # Keep birth_date empty if parsing fails
        
        # Extract encounters / presentations
        encounter_links = soup.find_all('a', href=re.compile(r'../files/presentation\.asp\?id='))
        for link in encounter_links:
            href = link.get('href', '')
            id_match = re.search(r'id=([^&"]+)', href)
            if id_match:
                patient_data["encounters"].append(id_match.group(1))
        
        # Extract admissions / checkins
        admission_links = soup.find_all('a', href=re.compile(r'../files/checkin\.asp\?id='))
        for link in admission_links:
            href = link.get('href', '')
            id_match = re.search(r'id=([^&"]+)', href)
            if id_match:
                patient_data["admissions"].append(id_match.group(1))
        
        # Extract discharges / checkouts
        discharge_links = soup.find_all('a', href=re.compile(r'../files/checkout\.asp\?id='))
        for link in discharge_links:
            href = link.get('href', '')
            id_match = re.search(r'id=([^&"]+)', href)
            if id_match:
                patient_data["discharges"].append(id_match.group(1))
        
        # Return the extracted patient data
        return patient_data
    except Exception as e:
        logger.error(f"Error parsing patient data: {e}")
        return {}

def convert_to_fhir_patient(patient_data: Dict[str, Any], request) -> Dict[str, Any]:
    """Convert patient data to FHIR Patient resource format.
    
    Args:
        patient_data: Patient data from parse_patient_data
        request: The HTTP request object to get the host
        
    Returns:
        FHIR Patient resource
    """
    # Use already extracted family name and given name if available
    family_name = patient_data.get("family_name", "")
    given_names = [patient_data.get("given_name", "")] if patient_data.get("given_name") else []
    
    # Fallback to parsing from full name if family/given names are not available
    if not family_name and not given_names:
        name_parts = patient_data.get("patient_name", "").split()
        family_name = name_parts[0] if len(name_parts) > 0 else ""
        given_names = name_parts[1:] if len(name_parts) > 1 else []
    
    # Use already extracted gender and birth date if available
    gender = patient_data.get("sex", "unknown")
    birth_date = patient_data.get("birth_date", "")
    
    # Fallback to deriving from CNP if gender/birth date are not available
    cnp = patient_data.get("patient_cnp", "")
    if (not gender or gender == "unknown") and cnp:
        parsed_cnp = parse_cnp(cnp)
        if parsed_cnp.get("valid"):
            gender = parsed_cnp.get("gender", "unknown")
    
    if not birth_date and cnp:
        parsed_cnp = parse_cnp(cnp)
        if parsed_cnp.get("valid"):
            birth_date = parsed_cnp.get("birth_date", "")
    
    # Create FHIR Patient resource
    fhir_patient = {
        "resourceType": "Patient",
        "id": patient_data.get("patient_id", ""),
        "meta": {
            "lastUpdated": datetime.now().isoformat()
        },
        "identifier": [
            {
                "system": f"http://{request.host}/fhir/NamingSystem/patient-id",
                "value": patient_data.get("patient_id", "")
            }
        ],
        "active": True,
        "name": [
            {
                "use": "official",
                "family": family_name,
                "given": given_names
            }
        ],
        "gender": gender,
        "birthDate": birth_date,
        "telecom": [],
        "address": []
    }

    # Add telecom information if available
    if patient_data.get("phone"):
        fhir_patient["telecom"].append({
            "system": "phone",
            "value": patient_data["phone"]
        })
    
    if patient_data.get("email"):
        fhir_patient["telecom"].append({
            "system": "email",
            "value": patient_data["email"]
        })

    # Add address information if available
    if patient_data.get("address"):
        fhir_patient["address"].append({
            "text": patient_data["address"]
        })

    # Add extensions for additional patient data
    fhir_patient["extension"] = []
    
    # Add CID if available
    if patient_data.get("cid"):
        fhir_patient["extension"].append({
            "url": f"http://{request.host}/fhir/StructureDefinition/patient-cid",
            "valueString": patient_data["cid"]
        })
    
    # Add weight if available
    if patient_data.get("weight"):
        fhir_patient["extension"].append({
            "url": f"http://{request.host}/fhir/StructureDefinition/patient-weight",
            "valueString": patient_data["weight"]
        })
    
    # Add height if available
    if patient_data.get("height"):
        fhir_patient["extension"].append({
            "url": f"http://{request.host}/fhir/StructureDefinition/patient-height",
            "valueString": patient_data["height"]
        })
    
    # Add MCP if available
    if patient_data.get("mcp"):
        fhir_patient["extension"].append({
            "url": f"http://{request.host}/fhir/StructureDefinition/patient-mcp",
            "valueString": patient_data["mcp"]
        })

    # Add extensions for encounter/admission/discharge IDs
    if "encounters" in patient_data:
        fhir_patient["extension"].append({
            "url": f"http://{request.host}/fhir/StructureDefinition/encounter-ids",
            "valueString": ",".join(patient_data["encounters"])
        })
    if "admissions" in patient_data:
        fhir_patient["extension"].append({
            "url": f"http://{request.host}/fhir/StructureDefinition/admission-ids",
            "valueString": ",".join(patient_data["admissions"])
        })
    if "discharges" in patient_data:
        fhir_patient["extension"].append({
            "url": f"http://{request.host}/fhir/StructureDefinition/discharge-ids",
            "valueString": ",".join(patient_data["discharges"])
        })
    
    # Add CNP as additional identifier if available
    if cnp:
        fhir_patient["identifier"].append({
            "system": f"http://{request.host}/fhir/NamingSystem/cnp",
            "value": cnp
        })
    
    # Return the FHIR Patient resource
    return fhir_patient

def parse_multiple_patients_data(html_content: str) -> List[Dict[str, Any]]:
    """Parse HTML content for multiple patient search results and extract patient data.
    
    Extracts patient names, CNP, and ids from search results page with multiple patients.
    
    Args:
        html_content: HTML content of the search results page
        
    Returns:
        List of dictionaries containing patient data (name, CNP, id only)
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Check if this is a search results page by looking for 'Fisier' in title
        if not is_expected_page(soup, 'Fisier'):
            return []
        
        patients = []
        
        # Find all table rows
        rows = soup.find_all('tr')
        
        for row in rows:
            # Look for the patient id link
            id_link = row.find('a', href=re.compile(r"javascript:Edit\('([^']+)'\);"))
            if not id_link:
                continue
                
            # Extract patient id
            id_href = id_link.get('href')
            id_match = re.search(r"javascript:Edit\('([^']+)'\);", id_href)
            if not id_match:
                continue
            patient_id = id_match.group(1)
            
            # Look for the patient name link (next link in the row)
            name_links = row.find_all('a')
            patient_name = ""
            for name_link in name_links:
                if name_link != id_link:
                    # Extract patient name
                    # Remove font tags and formatting
                    name_text = name_link.get_text()
                    # Clean up the name (remove extra spaces, normalize)
                    patient_name = re.sub(r'\s+', ' ', name_text.strip())
                    break
            
            # Look for CNP in the row (text input field with CNP)
            patient_cnp = ""
            cnp_inputs = row.find_all('input', type='text')
            for cnp_input in cnp_inputs:
                # Check if this input is for CNP by looking at surrounding context
                parent = cnp_input.find_parent('td')
                if parent and parent.find_previous_sibling('td'):
                    prev_td = parent.find_previous_sibling('td')
                    if prev_td and 'cnp' in prev_td.get_text().lower():
                        patient_cnp = cnp_input.get('value', '').strip()
                        break
            
            # Only add patient if we have at least a name or id
            if patient_name or patient_id:
                patient_data = {
                    "patient_name": patient_name,
                    "patient_cnp": patient_cnp,  # CNP
                    "patient_id": patient_id
                }
                patients.append(patient_data)
        
        return patients
    except Exception as e:
        logger.error(f"Error parsing multiple patients data: {e}")
        return []

def parse_checkout_data(html_content: str) -> Dict[str, Any]:
    """Parse HTML checkout content and extract structured data.
    
    Extracts patient information and medical data from checkout HTML content.
    
    Args:
        html_content: HTML content of the checkout page
        
    Returns:
        Dictionary containing parsed checkout data
    """
    import re
    from bs4 import BeautifulSoup
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Initialize result dictionary
        checkout_data = {
            "patient_name": "",
            "patient_cnp": "",
            "patient_id": "",
            "admission_diagnostic": "",
            "epicrisis": "",
            "diagnostic": "",
            "surgery": "",
            "recommendations": ""
        }
        
        # Extract patient name and ID from the link
        patient_link = soup.find('a', href=re.compile(r'../Pacient/edit\.asp\?id='))
        if patient_link:
            checkout_data["patient_name"] = patient_link.get_text().strip()
            # Extract patient ID from href
            href = patient_link.get('href', '')
            id_match = re.search(r'id=([^&"]+)', href)
            if id_match:
                checkout_data["patient_id"] = id_match.group(1).strip()
        
        # Extract patient id (Cod pacient)
        code_elements = soup.find_all('td', string=re.compile(r'Cod pacient\s*:', re.IGNORECASE))
        for code_element in code_elements:
            next_td = code_element.find_next('td')
            if next_td:
                checkout_data["patient_id"] = next_td.get_text().strip()
                break
        
        # Extract admission diagnostic
        diag_elements = soup.find_all('td', string=re.compile(r'Diagnostic\s*:', re.IGNORECASE))
        for diag_element in diag_elements:
            next_td = diag_element.find_next('td')
            if next_td:
                checkout_data["admission_diagnostic"] = next_td.get_text().strip()
                break
        
        # Extract epicrisis (first textarea after 'Epicriza:')
        checkout_data["epicrisis"] = get_textarea_content_after_label(soup, r'Epicriza[^:]*:')
        
        # Extract diagnostic (textarea after 'Diagnostic externare')
        checkout_data["diagnostic"] = get_textarea_content_after_label(soup, r'Diagnostic externare[^:]*:')
        
        # Extract surgery (textarea after 'Protocol operator:')
        checkout_data["surgery"] = get_textarea_content_after_label(soup, r'Protocol operator[^:]*:')
        
        # Extract recommendations (textarea after 'Recomandari')
        checkout_data["recommendations"] = get_textarea_content_after_label(soup, r'Recomandari[^:]*:')
        
        return checkout_data
    except Exception as e:
        logger.error(f"Error parsing checkout data: {e}")
        return {}

async def fhir_patient_read(request):
    """Retrieve patient information by ID.
    
    Gets patient information from the Hipocrate service and extracts
    associated admission and discharge IDs.
    
    Args:
        request: The incoming HTTP request with 'id' query parameter for patient ID
                 and optional X-Username and X-Password headers for authentication
        
    Returns:
        JSON response with patient data or error information
    """
    patient_id = request.match_info.get('id')
    logger.info(f"GET /fhir/Patient/{patient_id} endpoint accessed")
    
    if not patient_id:
        logger.warning("No patient ID provided")
        return create_error_response("Patient ID is required (not CNP)")
    
    logger.info(f"Retrieving patient with ID: {patient_id}")
    
    # Get credentials from request headers (optional)
    username = request.headers.get("X-Username")
    password = request.headers.get("X-Password")
    
    try:
        session = await get_session()
        
        # Make request to the patient endpoint
        patient_url = f"{SERVICE_URL}/Pacient/edit.asp?id={patient_id}"
        
        response_text, success, error_response = await make_authenticated_request(
            session, patient_url, "GET", None, username, password
        )
        # Check for errors in the response
        if not success:
            return error_response
        
        # For FHIR endpoint, we need to get patient details first
        patient_data = parse_patient_data(response_text)
        if patient_data and patient_data.get("patient_name"):
            fhir_patient = convert_to_fhir_patient(patient_data, request)
            return web.json_response(fhir_patient)
        else:
            if 'error' in patient_data:
                return create_error_response(patient_data['error'], 404)
            # Return an error if we couldn't read patient data
            return create_error_response("Unable to read patient data", 500)
            
    except Exception as e:
        logger.error(f"Patient retrieval failed with exception: {e}")
        return create_error_response(str(e), 500)

async def fhir_encounter_read(request):
    """Retrieve encounter information by ID.
    
    Gets encounter information from the Hipocrate service and parses
    the medical data into structured format.
    
    Args:
        request: The incoming HTTP request with 'identifier' query parameter for encounter ID
                 and optional X-Username and X-Password headers for authentication
        
    Returns:
        JSON response with encounter data or error information
    """
    encounter_id = request.query.get('identifier')
    logger.info(f"GET /fhir/Encounter endpoint accessed with identifier: {encounter_id}")
    
    if not encounter_id:
        logger.warning("No encounter ID provided")
        return create_error_response("Encounter ID is required")
    
    logger.info(f"Retrieving encounter with ID: {encounter_id}")
    
    # Get credentials from request headers (optional)
    username = request.headers.get("X-Username")
    password = request.headers.get("X-Password")
    
    try:
        session = await get_session()
        
        # Make request to the checkout endpoint
        checkout_url = f"{SERVICE_URL}/files/checkout.asp?id={encounter_id}"
        
        response_text, success, error_response = await make_authenticated_request(
            session, checkout_url, "GET", None, username, password
        )
        
        if not success:
            return error_response
        
        logger.info("Encounter retrieval completed successfully")
        # Parse the checkout data
        parsed_data = parse_checkout_data(response_text)
        
        # Create enhanced FHIR Encounter resource
        fhir_encounter = {
            "resourceType": "Encounter",
            "id": encounter_id,
            "meta": {
                "lastUpdated": datetime.now().isoformat()
            },
            "status": "finished",
            "class": {
                "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                "code": "IMP",
                "display": "inpatient encounter"
            },
            "type": [
                {
                    "coding": [
                        {
                            "system": "http://snomed.info/sct",
                            "code": "305056002",
                            "display": "Admission to hospital"
                        }
                    ]
                }
            ],
            "subject": {
                "reference": f"Patient/{parsed_data.get('patient_id', '')}"
            },
            "participant": []
        }
        
        # Add performer if available
        if parsed_data.get("examiner"):
            fhir_encounter["participant"].append({
                "type": [
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/v3-ParticipationType",
                                "code": "ATND",
                                "display": "attender"
                            }
                        ]
                    }
                ],
                "individual": {
                    "display": parsed_data["examiner"]
                }
            })
        
        # Add reason (admission diagnostic) if available
        if parsed_data.get("admission_diagnostic"):
            fhir_encounter["reasonCode"] = [
                {
                    "text": parsed_data["admission_diagnostic"]
                }
            ]
        
        # Add text summary if epicrisis exists
        if parsed_data.get("epicrisis"):
            fhir_encounter["text"] = {
                "status": "generated",
                "div": f"<div xmlns=\"http://www.w3.org/1999/xhtml\">{parsed_data['epicrisis']}</div>"
            }
            
            # Also add as a note
            fhir_encounter["note"] = [
                {
                    "text": parsed_data["epicrisis"]
                }
            ]
        
        # Add diagnosis if available
        if parsed_data.get("diagnostic"):
            fhir_encounter["diagnosis"] = [
                {
                    "condition": {
                        "display": parsed_data["diagnostic"]
                    },
                    "use": {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/diagnosis-role",
                                "code": "DD",
                                "display": "Discharge diagnosis"
                            }
                        ]
                    }
                }
            ]
        
        return web.json_response(fhir_encounter)
            
    except Exception as e:
        logger.error(f"Encounter retrieval failed with exception: {e}")
        return create_error_response(str(e), 500)

def parse_analyses_data(html_content: str) -> Dict[str, Any]:
    """Parse HTML analyses content and extract analysis IDs, analysis types, patient name, and patient id.
    
    Extracts patient name, patient id, and list of analyses with their types and analysis IDs
    from the analyses HTML page.
    
    Args:
        html_content: HTML content of the analyses page
        
    Returns:
        Dictionary containing patient name, patient id, and list of analyses
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Check if this is the correct page by looking for 'Cereri de Laborator' in title
        if not is_expected_page(soup, 'Cereri de Laborator'):
            logger.warning("Page is not a laboratory requests page")
            return {"patient_name": "", "patient_id": "", "analyses": []}
        
        # Initialize result
        result = {
            "patient_name": "",
            "patient_id": "",
            "analyses": []
        }
        
        # Extract patient name and id from the link pattern
        patient_link = soup.find('a', href=re.compile(r'../Pacient/edit\.asp\?id=\d+'))
        if patient_link:
            result["patient_name"] = patient_link.get_text().strip()
            # Extract patient id from href
            href = patient_link.get('href', '')
            code_match = re.search(r'id=(\d+)', href)
            if code_match:
                result["patient_id"] = code_match.group(1)
        
        # Extract CNP from table (next TD after 'CNP:')
        cnp_cells = soup.find_all('td', string=re.compile(r'CNP:', re.IGNORECASE))
        for cnp_cell in cnp_cells:
            next_td = cnp_cell.find_next('td')
            if next_td:
                cnp_text = next_td.get_text().strip()
                if cnp_text and cnp_text.isdigit() and len(cnp_text) == 13:
                    result["patient_cnp"] = cnp_text
                    break
        
        # Find all links to analysis analysis
        analysis_links = soup.find_all('a', href=re.compile(r'../analyse/Reports/analyseFile\.asp\?id=\d+'))
        
        for link in analysis_links:
            # Extract analysis ID
            href = link.get('href', '')
            id_match = re.search(r'id=(\d+)', href)
            if not id_match:
                continue
            
            analysis_id = id_match.group(1)
            
            # Find the parent table row
            parent_row = link.find_parent('tr')
            if not parent_row:
                # If no parent row, just add the ID without type
                result["analyses"].append({
                    "analysis_id": analysis_id,
                    "type": "unknown"
                })
                continue
            
            # Extract information from table cells
            analysis_data = {
                "analysis_id": analysis_id,
                "type": "unknown"
            }
            
            cells = parent_row.find_all('td')
            if len(cells) >= 8:
                # Cell 0: Checkbox (ignore)
                # Cell 1: Report link (already processed)
                # Cell 2: Barcode (ignore)
                # Cell 3: Checkin code
                checkin_link = cells[3].find('a', href=re.compile(r'/files/checkin\.asp\?id=\d+'))
                if checkin_link:
                    checkin_href = checkin_link.get('href', '')
                    checkin_match = re.search(r'id=(\d+)', checkin_href)
                    if checkin_match:
                        analysis_data["admission"] = checkin_match.group(1)
                
                # Cell 4: Date
                date_text = cells[4].get_text().strip()
                if date_text:
                    analysis_data["date"] = date_text
                    # Try to parse the date string into a proper datetime object
                    try:
                        # Handle common date formats like "07 Nov 2025 10:29:00"
                        # Create a mapping for Romanian month abbreviations to English ones
                        month_mapping = {
                            'Ian': 'Jan', 'Mai': 'May', 'Iun': 'Jun', 'Iul': 'Jul'
                        }
                        
                        # Replace Romanian month abbreviations with English ones
                        formatted_date = date_text
                        for ro_month, en_month in month_mapping.items():
                            formatted_date = formatted_date.replace(ro_month, en_month)
                        
                        # Parse the datetime using strptime
                        analysis_data["datetime"] = datetime.strptime(formatted_date, '%d %b %Y %H:%M:%S')
                    except Exception as e:
                        logger.debug(f"Could not parse datetime from string '{date_text}': {e}")
                        # Keep the original string if parsing fails
                
                # Cell 5: Priority
                priority_text = cells[5].get_text().strip()
                if priority_text:
                    analysis_data["priority"] = priority_text
                
                # Cell 6: Analysis type
                type_text = cells[6].get_text().strip()
                # Look for pattern like 'XXXX-Radio', 'XXXX-lab', etc.
                type_match = re.search(r'\d{4}-(\w+)', type_text)
                if type_match:
                    extracted_type = type_match.group(1).lower()
                    # Check if the extracted type is in our known analysis types
                    if extracted_type in ANALYSIS_TYPES:
                        analysis_data["type"] = extracted_type
                    else:
                        analysis_data["type"] = "unknown"
                else:
                    analysis_data["type"] = "unknown"
                
                # Cell 7: Requesting doctor
                doctor_text = cells[7].get_text().strip()
                if doctor_text:
                    analysis_data["requesting_doctor"] = doctor_text
            
            result["analyses"].append(analysis_data)
        
        return result
    except Exception as e:
        logger.error(f"Error parsing analyses data: {e}")
        return {"patient_name": "", "patient_id": "", "analyses": []}

async def fhir_observation_search(request):
    """Retrieve list of observations for a patient by ID.
    
    Gets a list of observations for a specific patient from the Hipocrate service
    without fetching detailed data for each observation.
    
    Args:
        request: The incoming HTTP request with 'patient' query parameter for patient ID
                 and optional X-Username and X-Password headers for authentication
        
    Returns:
        JSON response with observations data or error information
    """
    patient_id = request.query.get('patient')
    logger.info(f"GET /fhir/Observation endpoint accessed for patient: {patient_id}")
    
    # Get credentials from request headers (optional)
    username = request.headers.get("X-Username")
    password = request.headers.get("X-Password")
    
    if not patient_id:
        logger.warning("No patient ID provided")
        return create_error_response("Patient ID is required")
    
    # Get optional parameters
    analysis_type = request.query.get('type')
    datetime_filter = request.query.get('dt')
    full_data = request.query.get('full', 'no').lower() == 'yes'
    
    logger.info(f"Retrieving analyses list for patient with ID: {patient_id}")
    
    try:
        session = await get_session()
        
        # Make request to the analyses endpoint
        analyses_url = f"{SERVICE_URL}/pacient/analyses.asp?type=PA&pacid={patient_id}"
        
        # Add full=yes parameter if requested
        if full_data:
            analyses_url += "&full=yes"
        
        start_time = datetime.now()
        response_text, success, error_response = await make_authenticated_request(
            session, analyses_url, "GET", None, username, password
        )
        duration = (datetime.now() - start_time).total_seconds()
        
        if not success:
            return error_response
        
        logger.info(f"Analyses list retrieval completed successfully in {duration:.2f} seconds")
        # Parse the analyses data to extract report IDs, types, and patient name
        parsed_data = parse_analyses_data(response_text)
        
        # Filter analyses by type if specified
        analyses = parsed_data["analyses"]
        if analysis_type:
            analyses = [a for a in analyses if a["type"] == analysis_type]
        
        # Create FHIR Bundle of Observation resources (minimal data only)
        bundle = {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": len(analyses),
            "entry": []
        }
        
        for analysis in analyses:
            fhir_observation = {
                "resourceType": "Observation",
                "id": analysis["analysis_id"],
                "meta": {
                    "lastUpdated": analysis["datetime"].isoformat() if "datetime" in analysis and analysis["datetime"] else datetime.now().isoformat()
                },
                "status": "final",
                "category": [
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                "code": "laboratory" if analysis["type"] == "lab" else "imaging",
                                "display": "Laboratory" if analysis["type"] == "lab" else "Imaging"
                            }
                        ]
                    }
                ],
                "code": {
                    "coding": [
                        {
                            "system": f"http://{request.host}/fhir/CodeSystem/analysis-types",
                            "code": analysis["type"],
                            "display": ANALYSIS_TYPES[analysis["type"]]["display"]
                        }
                    ],
                    "text": ANALYSIS_TYPES[analysis["type"]]["definition"]
                },
                "subject": {
                    "reference": f"Patient/{patient_id}"
                }
            }
            
            bundle["entry"].append({
                "resource": fhir_observation
            })
        
        return web.json_response(bundle)
            
    except Exception as e:
        logger.error(f"Analyses list retrieval failed with exception: {e}")
        return create_error_response(str(e), 500)

async def fhir_observation_read(request):
    """Retrieve a single observation by ID.
    
    Gets detailed information for a specific observation from the Hipocrate service.
    
    Args:
        request: The incoming HTTP request with 'id' path parameter for observation ID
                 and optional X-Username and X-Password headers for authentication
        
    Returns:
        JSON response with observation data or error information
    """
    observation_id = request.match_info.get('id')
    logger.info(f"GET /fhir/Observation/{observation_id} endpoint accessed")
    
    # Get credentials from request headers (optional)
    username = request.headers.get("X-Username")
    password = request.headers.get("X-Password")
    
    if not observation_id:
        logger.warning("No observation ID provided")
        return create_error_response("Observation ID is required")
    
    logger.info(f"Retrieving observation with ID: {observation_id}")
    
    try:
        session = await get_session()
        
        # Get patient ID from query parameter or derive it
        patient_id = request.query.get('patient', '')
        
        # Get report details to extract observation data
        report_url = f"{SERVICE_URL}/analyse/Reports/analyseFile.asp?id={observation_id}"
        report_text, success, error_response = await make_authenticated_request(
            session, report_url, "GET", None, username, password
        )
        
        if not success:
            return error_response
        
        # Parse report to get observation data
        report_data = parse_report_data(report_text)
        
        fhir_observation = {
            "resourceType": "Observation",
            "id": observation_id,
            "meta": {
                "lastUpdated": datetime.now().isoformat()
            },
            "status": "final",
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                            "code": "imaging",
                            "display": "Imaging"
                        }
                    ]
                }
            ],
            "code": {
                "coding": [
                    {
                        "system": f"http://{request.host}/fhir/CodeSystem/analysis-types",
                        "code": "unknown",  # Will be updated based on report data
                        "display": "Analysis"
                    }
                ],
                "text": report_data.get("examination", "Analysis")
            },
            "subject": {
                "reference": f"Patient/{report_data.get('patient_id', patient_id)}"
            }
        }
        
        # Add effective datetime if available
        if report_data.get("sample_datetime"):
            fhir_observation["effectiveDateTime"] = report_data["sample_datetime"]
        
        # Add performer if available
        if report_data.get("examiner"):
            fhir_observation["performer"] = [
                {
                    "display": report_data["examiner"]
                }
            ]
        
        # Add patient gender and birth date if available
        if report_data.get("gender"):
            fhir_observation["extension"] = [
                {
                    "url": "http://hl7.org/fhir/StructureDefinition/patient-gender",
                    "valueCode": report_data["gender"].lower()
                }
            ]
        
        if report_data.get("birth_date"):
            if "extension" not in fhir_observation:
                fhir_observation["extension"] = []
            fhir_observation["extension"].append({
                "url": "http://hl7.org/fhir/StructureDefinition/patient-birthDate",
                "valueDate": report_data["birth_date"]
            })
        
        # Add value/comment if available
        if report_data.get("reports"):
            # For now, add the first report result as a comment
            first_report = report_data["reports"][0] if report_data["reports"] else None
            if first_report and first_report.get("result"):
                fhir_observation["note"] = [
                    {
                        "text": first_report["result"]
                    }
                ]
        
        return web.json_response(fhir_observation)
            
    except Exception as e:
        logger.error(f"Observation retrieval failed with exception: {e}")
        return create_error_response(str(e), 500)

def parse_cnp(cnp: str) -> Dict[str, Any]:
    """Parse a Romanian CNP (Personal Numerical Code) and extract meaningful data.
    
    Extracts gender, birth date, county, and other information from a valid CNP.
    
    Args:
        cnp: The CNP to parse
        
    Returns:
        Dictionary with parsed data including:
            - valid: bool - whether the CNP is valid
            - gender: str - male/female
            - birth_date: str - ISO format date (YYYY-MM-DD)
            - county_code: int - county code
            - county_name: str - county name
            - serial: str - serial number
            - control_digit: int - control digit
    """
    # Check if CNP is exactly 13 digits
    if not cnp or len(cnp) != 13 or not cnp.isdigit():
        return {"valid": False}
    
    # Extract components
    gender_digit = int(cnp[0])
    year = int(cnp[1:3])
    month = int(cnp[3:5])
    day = int(cnp[5:7])
    county_code = int(cnp[7:9])
    serial = cnp[9:12]
    control_digit = int(cnp[12])
    
    # County codes mapping
    county_names = {
        1: "Alba", 2: "Arad", 3: "Argeș", 4: "Bacău", 5: "Bihor", 6: "Bistrița-Năsăud",
        7: "Botoșani", 8: "Brașov", 9: "Brăila", 10: "Buzău", 11: "Caraș-Severin",
        12: "Cluj", 13: "Constanța", 14: "Covasna", 15: "Dâmbovița", 16: "Dolj",
        17: "Galați", 18: "Gorj", 19: "Harghita", 20: "Hunedoara", 21: "Ialomița",
        22: "Iași", 23: "Ilfov", 24: "Maramureș", 25: "Mehedinți", 26: "Mureș",
        27: "Neamț", 28: "Olt", 29: "Prahova", 30: "Satu Mare", 31: "Sălaj",
        32: "Sibiu", 33: "Suceava", 34: "Teleorman", 35: "Timiș", 36: "Tulcea",
        37: "Vaslui", 38: "Vâlcea", 39: "Vrancea", 40: "București", 41: "București",
        42: "București", 43: "București", 44: "București", 45: "București", 46: "București",
        51: "Călărași", 52: "Giurgiu",
        70: "Diaspora", 71: "Diaspora", 72: "Diaspora", 73: "Diaspora", 74: "Diaspora",
        75: "Diaspora", 76: "Diaspora", 77: "Diaspora", 78: "Diaspora", 79: "Diaspora",
        90: "Special", 91: "Special", 92: "Special", 93: "Special", 94: "Special",
        95: "Special", 96: "Special", 97: "Special", 98: "Special", 99: "Special"
    }
    
    # Validate gender digit (1-8 are valid)
    if gender_digit < 1 or gender_digit > 8:
        return {"valid": False}
    
    # Validate month (1-12)
    if month < 1 or month > 12:
        return {"valid": False}
    
    # Validate day (1-31)
    if day < 1 or day > 31:
        return {"valid": False}
    
    # Validate county code (1-52, excluding 47-50, plus 70-79 for diaspora, 90-99 for special cases)
    if not ((1 <= county_code <= 52 and not (47 <= county_code <= 50)) or 
            (70 <= county_code <= 79) or 
            (90 <= county_code <= 99)):
        return {"valid": False}
    
    # Validate date by trying to create a datetime object
    try:
        # Determine century based on gender digit
        if gender_digit in [1, 2]:
            full_year = 1900 + year
        elif gender_digit in [3, 4]:
            full_year = 1800 + year
        elif gender_digit in [5, 6]:
            full_year = 2000 + year
        else:  # 7, 8
            full_year = 2000 + year  # For people born after 2000
        
        # Check if date is valid
        birth_date = datetime(full_year, month, day)
    except ValueError:
        return {"valid": False}
    
    # Validate control digit using checksum
    weights = [2, 7, 9, 1, 4, 6, 3, 5, 8, 2, 7, 9]
    checksum = sum(int(cnp[i]) * weights[i] for i in range(12)) % 11
    calculated_control_digit = 1 if checksum == 10 else checksum
    
    if calculated_control_digit != control_digit:
        return {"valid": False}
    
    # Determine gender
    gender = "male" if gender_digit in [1, 3, 5, 7] else "female"
    
    # Get county name
    county_name = county_names.get(county_code, "Unknown")
    
    return {
        "valid": True,
        "gender": gender,
        "birth_date": birth_date.strftime('%Y-%m-%d'),
        "county_code": county_code,
        "county_name": county_name,
        "serial": serial,
        "control_digit": control_digit
    }

def validate_cnp(cnp: str) -> bool:
    """Validate a Romanian CNP (Personal Numerical Code).
    
    Checks if the provided string is a valid Romanian CNP by verifying:
    - Length (13 digits)
    - Gender digit (1-8)
    - Date components (year, month, day)
    - County code (1-52, excluding 47-50)
    - Control digit using checksum algorithm
    
    Args:
        cnp: The CNP to validate
        
    Returns:
        True if CNP is valid, False otherwise
    """
    parsed_data = parse_cnp(cnp)
    return parsed_data.get("valid", False)

async def fhir_cnp_validate(request):
    """Validate a Romanian CNP (Personal Numerical Code).
    
    Validates a Romanian CNP using the internal validation algorithm and returns parsed data.
    
    Args:
        request: The incoming HTTP request with 'id' query parameter for CNP
        
    Returns:
        JSON response with validation result and parsed data
    """
    logger.info("GET /fhir/ValueSet/cnp endpoint accessed")
    
    # Get CNP from query string
    cnp = request.query.get('id')
    
    if not cnp:
        logger.warning("No CNP provided")
        return create_error_response("CNP is required")
    
    logger.info(f"Validating CNP: {cnp}")
    
    # Parse CNP to get detailed information
    parsed_data = parse_cnp(cnp)
    
    response_data = {
        "status": "success",
        "cnp": cnp,
        "valid": parsed_data.get("valid", False)
    }
    
    # Add parsed data if valid
    if parsed_data.get("valid"):
        response_data.update({
            "gender": parsed_data.get("gender"),
            "birth_date": parsed_data.get("birth_date"),
            "county_code": parsed_data.get("county_code"),
            "county_name": parsed_data.get("county_name"),
            "serial": parsed_data.get("serial"),
            "control_digit": parsed_data.get("control_digit")
        })
    
    return web.json_response(response_data)

def markdown_to_html(markdown_text: str) -> str:
    """Convert simple markdown to basic HTML.
    
    Supports:
    - Paragraphs (double newlines)
    - Line breaks (single newlines)
    - Bold text (**text** or __text__)
    - Italic text (*text* or _text_)
    - Headers (# Header, ## Header, etc.)
    - Unordered lists (- item or * item)
    - Ordered lists (1. item, 2. item, etc.)
    
    Args:
        markdown_text: Markdown text to convert
        
    Returns:
        HTML representation of the markdown
    """
    import re
    
    # Escape HTML characters
    html = markdown_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    # Headers (# Header, ## Header, etc.)
    html = re.sub(r'^###### (.*)$', r'<h6>\1</h6>', html, flags=re.MULTILINE)
    html = re.sub(r'^##### (.*)$', r'<h5>\1</h5>', html, flags=re.MULTILINE)
    html = re.sub(r'^#### (.*)$', r'<h4>\1</h4>', html, flags=re.MULTILINE)
    html = re.sub(r'^### (.*)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.*)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.*)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
    
    # Bold (**text** or __text__)
    html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'__(.*?)__', r'<strong>\1</strong>', html)
    
    # Italic (*text* or _text_)
    html = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html)
    html = re.sub(r'_(.*?)_', r'<em>\1</em>', html)
    
    # Unordered lists (- item or * item)
    html = re.sub(r'^\s*[-*]\s+(.*)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'(<li>.*</li>\s*)+', r'<ul>\n\g<0></ul>\n', html)
    
    # Ordered lists (1. item, 2. item, etc.)
    html = re.sub(r'^\s*\d+\.\s+(.*)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'(<li>.*</li>\s*)+', r'<ol>\n\g<0></ol>\n', html)
    
    # Paragraphs (separated by double newlines)
    paragraphs = html.split('\n\n')
    html = '\n'.join([f'<p>{p}</p>' if not p.startswith(('<h', '<ul', '<ol')) else p for p in paragraphs if p.strip()])
    
    # Line breaks (single newlines within paragraphs)
    html = html.replace('\n', '<br>')
    
    return html

async def fhir_markdown_to_html(request):
    """Convert markdown text to HTML.
    
    Takes markdown text and converts it to basic HTML.
    
    Args:
        request: The incoming HTTP request with JSON body containing 'text' field
        
    Returns:
        JSON response with HTML content
    """
    logger.info("POST /fhir/md2html endpoint accessed")
    
    try:
        # Get markdown text from request body
        data = await request.json()
        markdown_text = data.get('text', '')
        
        html_content = markdown_to_html(markdown_text)
        
        return web.json_response({
            "status": "success",
            "html": html_content
        })
    except json.JSONDecodeError:
        logger.warning("Invalid JSON data received for markdown conversion")
        return create_error_response("Invalid JSON data")
    except Exception as e:
        logger.error(f"Markdown conversion failed: {e}")
        return create_error_response(str(e), 500)

async def fhir_analysis_types(request):
    """Serve the analysis types terminology.
    
    Returns a FHIR CodeSystem resource defining the analysis types used in the hospital system.
    
    Args:
        request: The incoming HTTP request
        
    Returns:
        JSON response with CodeSystem resource
    """
    logger.info("GET /fhir/CodeSystem/analysis-types endpoint accessed")
    
    # Build concepts list using for loop
    concepts = []
    for code, details in ANALYSIS_TYPES.items():
        concepts.append({
            "code": code,
            "display": details["display"],
            "definition": details["definition"]
        })
    
    code_system = {
        "resourceType": "CodeSystem",
        "id": "analysis-types",
        "url": f"http://{request.host}/fhir/CodeSystem/analysis-types",
        "version": "1.0.0",
        "name": "HospitalAnalysisTypes",
        "title": "Hospital Analysis Types",
        "status": "active",
        "experimental": False,
        "date": datetime.now().strftime('%Y-%m-%d'),
        "publisher": "Hospital System",
        "description": "Code system for analysis types used in the hospital",
        "caseSensitive": True,
        "content": "complete",
        "concept": concepts
    }
    
    return web.json_response(code_system)

async def fhir_specification(request):
    """Serve the OpenAPI specification.
    
    Returns the OpenAPI specification in JSON format for API documentation.
    
    Args:
        request: The incoming HTTP request
        
    Returns:
        JSON response with OpenAPI specification
    """
    logger.info("GET /fhir/spec endpoint accessed")
    
    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "Hipocrate Patient Analyzer API (FHIR)",
            "description": "FHIR-compatible API for accessing patient data from the Hipocrate medical system",
            "version": "1.0.0"
        },
        "servers": [
            {
                "url": f"http://localhost:{PORT}",
                "description": "Local development server"
            }
        ],
        "paths": {
            "/": {
                "get": {
                    "summary": "Web interface",
                    "description": "Returns the web interface for patient analysis",
                    "responses": {
                        "200": {
                            "description": "HTML web interface"
                        }
                    }
                }
            },
            "/fhir/login": {
                "post": {
                    "summary": "Login to Hipocrate system",
                    "description": "Authenticate with the Hipocrate medical system",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "username": {
                                            "type": "string",
                                            "description": "Username for Hipocrate system"
                                        },
                                        "password": {
                                            "type": "string",
                                            "description": "Password for Hipocrate system"
                                        }
                                    },
                                    "required": ["username", "password"]
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Successful login",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "example": "success"
                                            },
                                            "message": {
                                                "type": "string",
                                                "example": "Login successful"
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "400": {
                            "description": "Missing credentials",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "example": "error"
                                            },
                                            "message": {
                                                "type": "string",
                                                "example": "Username and password are required"
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "401": {
                            "description": "Login failed",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "example": "error"
                                            },
                                            "message": {
                                                "type": "string",
                                                "example": "Login failed"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/fhir/md2html": {
                "post": {
                    "summary": "Convert markdown to HTML",
                    "description": "Convert simple markdown text to basic HTML",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "text": {
                                            "type": "string",
                                            "description": "Markdown text to convert"
                                        }
                                    },
                                    "required": ["text"]
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "HTML conversion result",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "example": "success"
                                            },
                                            "html": {
                                                "type": "string"
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "500": {
                            "description": "Conversion error",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "example": "error"
                                            },
                                            "message": {
                                                "type": "string"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/fhir/Patient": {
                "get": {
                    "summary": "Search for patients",
                    "description": "Search for patients by name, CNP, or patient code. Returns FHIR Patient resources.",
                    "parameters": [
                        {
                            "name": "q",
                            "in": "query",
                            "required": True,
                            "description": "Search term (patient name, CNP, patient code, or partial CNP ending with *)",
                            "schema": {
                                "type": "string"
                            }
                        },
                        {
                            "name": "X-Username",
                            "in": "header",
                            "required": False,
                            "description": "Username for authentication",
                            "schema": {
                                "type": "string"
                            }
                        },
                        {
                            "name": "X-Password",
                            "in": "header",
                            "required": False,
                            "description": "Password for authentication",
                            "schema": {
                                "type": "string"
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Search results as FHIR Patient resource or Bundle",
                            "content": {
                                "application/fhir+json": {
                                    "schema": {
                                        "oneOf": [
                                            {
                                                "type": "object",
                                                "properties": {
                                                    "resourceType": {
                                                        "type": "string",
                                                        "example": "Patient"
                                                    }
                                                }
                                            },
                                            {
                                                "type": "object",
                                                "properties": {
                                                    "resourceType": {
                                                        "type": "string",
                                                        "example": "Bundle"
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                }
                            }
                        },
                        "400": {
                            "description": "Missing search term",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "example": "error"
                                            },
                                            "message": {
                                                "type": "string",
                                                "example": "Search term is required"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/fhir/Patient/{id}": {
                "get": {
                    "summary": "Get patient information",
                    "description": "Retrieve patient information by ID as FHIR Patient resource",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "description": "Patient ID",
                            "schema": {
                                "type": "string"
                            }
                        },
                        {
                            "name": "X-Username",
                            "in": "header",
                            "required": False,
                            "description": "Username for authentication",
                            "schema": {
                                "type": "string"
                            }
                        },
                        {
                            "name": "X-Password",
                            "in": "header",
                            "required": False,
                            "description": "Password for authentication",
                            "schema": {
                                "type": "string"
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Patient information as FHIR Patient resource",
                            "content": {
                                "application/fhir+json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "resourceType": {
                                                "type": "string",
                                                "example": "Patient"
                                            },
                                            "id": {
                                                "type": "string"
                                            },
                                            "identifier": {
                                                "type": "array"
                                            },
                                            "name": {
                                                "type": "array"
                                            },
                                            "gender": {
                                                "type": "string"
                                            },
                                            "birthDate": {
                                                "type": "string"
                                            },
                                            "extension": {
                                                "type": "array"
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "400": {
                            "description": "Missing patient ID",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "example": "error"
                                            },
                                            "message": {
                                                "type": "string",
                                                "example": "Patient ID is required"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/fhir/Observation": {
                "get": {
                    "summary": "Get patient analyses",
                    "description": "Retrieve all analyses for a patient as FHIR Observation resources with optional filtering by type and datetime",
                    "parameters": [
                        {
                            "name": "patient",
                            "in": "query",
                            "required": True,
                            "description": "Patient ID",
                            "schema": {
                                "type": "string"
                            }
                        },
                        {
                            "name": "type",
                            "in": "query",
                            "required": False,
                            "description": "Analysis type to filter by (e.g., radio, ct, irm, eco, lab, lac, lii, rads, apa)",
                            "schema": {
                                "type": "string"
                            }
                        },
                        {
                            "name": "dt",
                            "in": "query",
                            "required": False,
                            "description": "Date/time filter in ISO format (YYYY-MM-DDTHH:mm:ss) - includes reports older than this but no older than 6 hours later",
                            "schema": {
                                "type": "string",
                                "format": "date-time"
                            }
                        },
                        {
                            "name": "X-Username",
                            "in": "header",
                            "required": False,
                            "description": "Username for authentication",
                            "schema": {
                                "type": "string"
                            }
                        },
                        {
                            "name": "X-Password",
                            "in": "header",
                            "required": False,
                            "description": "Password for authentication",
                            "schema": {
                                "type": "string"
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Patient analyses as FHIR Bundle of Observation resources",
                            "content": {
                                "application/fhir+json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "resourceType": {
                                                "type": "string",
                                                "example": "Bundle"
                                            },
                                            "entry": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "resource": {
                                                            "type": "object",
                                                            "properties": {
                                                                "resourceType": {
                                                                    "type": "string",
                                                                    "example": "Observation"
                                                                }
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "400": {
                            "description": "Missing patient ID",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "example": "error"
                                            },
                                            "message": {
                                                "type": "string",
                                                "example": "Patient ID is required"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/fhir/Observation/{id}": {
                "get": {
                    "summary": "Get a single observation",
                    "description": "Retrieve a single observation by ID as FHIR Observation resource",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "description": "Observation ID",
                            "schema": {
                                "type": "string"
                            }
                        },
                        {
                            "name": "X-Username",
                            "in": "header",
                            "required": False,
                            "description": "Username for authentication",
                            "schema": {
                                "type": "string"
                            }
                        },
                        {
                            "name": "X-Password",
                            "in": "header",
                            "required": False,
                            "description": "Password for authentication",
                            "schema": {
                                "type": "string"
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Observation as FHIR Observation resource",
                            "content": {
                                "application/fhir+json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "resourceType": {
                                                "type": "string",
                                                "example": "Observation"
                                            },
                                            "id": {
                                                "type": "string"
                                            },
                                            "status": {
                                                "type": "string"
                                            },
                                            "category": {
                                                "type": "array"
                                            },
                                            "code": {
                                                "type": "object"
                                            },
                                            "subject": {
                                                "type": "object"
                                            },
                                            "effectiveDateTime": {
                                                "type": "string"
                                            },
                                            "performer": {
                                                "type": "array"
                                            },
                                            "note": {
                                                "type": "array"
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "400": {
                            "description": "Missing observation ID",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "example": "error"
                                            },
                                            "message": {
                                                "type": "string",
                                                "example": "Observation ID is required"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/fhir/DiagnosticReport": {
                "get": {
                    "summary": "Get analysis report",
                    "description": "Retrieve an analysis report by ID as FHIR DiagnosticReport resource",
                    "parameters": [
                        {
                            "name": "identifier",
                            "in": "query",
                            "required": True,
                            "description": "Report ID",
                            "schema": {
                                "type": "string"
                            }
                        },
                        {
                            "name": "X-Username",
                            "in": "header",
                            "required": False,
                            "description": "Username for authentication",
                            "schema": {
                                "type": "string"
                            }
                        },
                        {
                            "name": "X-Password",
                            "in": "header",
                            "required": False,
                            "description": "Password for authentication",
                            "schema": {
                                "type": "string"
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Analysis report as FHIR DiagnosticReport resource",
                            "content": {
                                "application/fhir+json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "resourceType": {
                                                "type": "string",
                                                "example": "DiagnosticReport"
                                            },
                                            "id": {
                                                "type": "string"
                                            },
                                            "status": {
                                                "type": "string"
                                            },
                                            "category": {
                                                "type": "array"
                                            },
                                            "code": {
                                                "type": "object"
                                            },
                                            "subject": {
                                                "type": "object"
                                            },
                                            "effectiveDateTime": {
                                                "type": "string"
                                            },
                                            "performer": {
                                                "type": "array"
                                            },
                                            "result": {
                                                "type": "array"
                                            },
                                            "conclusion": {
                                                "type": "string"
                                            },
                                            "media": {
                                                "type": "array"
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "400": {
                            "description": "Missing report ID",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "example": "error"
                                            },
                                            "message": {
                                                "type": "string",
                                                "example": "Report ID is required"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/fhir/Encounter": {
                "get": {
                    "summary": "Get checkout information",
                    "description": "Retrieve checkout information by ID as FHIR Encounter resource",
                    "parameters": [
                        {
                            "name": "identifier",
                            "in": "query",
                            "required": True,
                            "description": "Checkout ID",
                            "schema": {
                                "type": "string"
                            }
                        },
                        {
                            "name": "X-Username",
                            "in": "header",
                            "required": False,
                            "description": "Username for authentication",
                            "schema": {
                                "type": "string"
                            }
                        },
                        {
                            "name": "X-Password",
                            "in": "header",
                            "required": False,
                            "description": "Password for authentication",
                            "schema": {
                                "type": "string"
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Checkout information as FHIR Encounter resource",
                            "content": {
                                "application/fhir+json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "resourceType": {
                                                "type": "string",
                                                "example": "Encounter"
                                            },
                                            "id": {
                                                "type": "string"
                                            },
                                            "status": {
                                                "type": "string"
                                            },
                                            "class": {
                                                "type": "object"
                                            },
                                            "type": {
                                                "type": "array"
                                            },
                                            "subject": {
                                                "type": "object"
                                            },
                                            "participant": {
                                                "type": "array"
                                            },
                                            "reasonCode": {
                                                "type": "array"
                                            },
                                            "diagnosis": {
                                                "type": "array"
                                            },
                                            "text": {
                                                "type": "object"
                                            },
                                            "note": {
                                                "type": "array"
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "400": {
                            "description": "Missing checkout ID",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "example": "error"
                                            },
                                            "message": {
                                                "type": "string",
                                                "example": "Checkout ID is required"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/fhir/ValueSet/cnp": {
                "get": {
                    "summary": "Validate CNP",
                    "description": "Validate a Romanian Personal Numerical Code (CNP) and return detailed information",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "query",
                            "required": True,
                            "description": "CNP to validate",
                            "schema": {
                                "type": "string"
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "CNP validation result with detailed information",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "example": "success"
                                            },
                                            "cnp": {
                                                "type": "string"
                                            },
                                            "valid": {
                                                "type": "boolean"
                                            },
                                            "gender": {
                                                "type": "string"
                                            },
                                            "birth_date": {
                                                "type": "string"
                                            },
                                            "county_code": {
                                                "type": "integer"
                                            },
                                            "county_name": {
                                                "type": "string"
                                            },
                                            "serial": {
                                                "type": "string"
                                            },
                                            "control_digit": {
                                                "type": "integer"
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "400": {
                            "description": "Missing CNP",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "example": "error"
                                            },
                                            "message": {
                                                "type": "string",
                                                "example": "CNP is required"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/fhir/CodeSystem/analysis-types": {
                "get": {
                    "summary": "Get analysis types",
                    "description": "Retrieve the FHIR CodeSystem resource defining the analysis types used in the hospital system",
                    "responses": {
                        "200": {
                            "description": "Analysis types as FHIR CodeSystem resource",
                            "content": {
                                "application/fhir+json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "resourceType": {
                                                "type": "string",
                                                "example": "CodeSystem"
                                            },
                                            "id": {
                                                "type": "string"
                                            },
                                            "url": {
                                                "type": "string"
                                            },
                                            "version": {
                                                "type": "string"
                                            },
                                            "name": {
                                                "type": "string"
                                            },
                                            "title": {
                                                "type": "string"
                                            },
                                            "status": {
                                                "type": "string"
                                            },
                                            "experimental": {
                                                "type": "boolean"
                                            },
                                            "date": {
                                                "type": "string"
                                            },
                                            "publisher": {
                                                "type": "string"
                                            },
                                            "description": {
                                                "type": "string"
                                            },
                                            "caseSensitive": {
                                                "type": "boolean"
                                            },
                                            "content": {
                                                "type": "string"
                                            },
                                            "concept": {
                                                "type": "array"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    
    return web.json_response(spec)

async def fhir_diagnostic_report_read(request):
    """Retrieve a diagnostic report by ID, following redirect chains.
    
    Gets a diagnostic report from the Hipocrate service, following any redirects to
    retrieve the final report data, then parses it into structured format.
    
    Args:
        request: The incoming HTTP request with 'identifier' query parameter for report ID
                 and optional X-Username and X-Password headers for authentication
        
    Returns:
        JSON response with diagnostic report data or error information
    """
    report_id = request.query.get('identifier')
    logger.info(f"GET /fhir/DiagnosticReport endpoint accessed with identifier: {report_id}")
    
    # Get credentials from request headers (optional)
    username = request.headers.get("X-Username")
    password = request.headers.get("X-Password")
    
    if not report_id:
        logger.warning("No report ID provided")
        return web.json_response({
            "status": "error",
            "message": "Report ID is required"
        }, status=400)
    
    logger.info(f"Retrieving report with ID: {report_id}")
    
    try:
        session = await get_session()
        
        # First ensure we're logged in
        login_success = await login_if_needed(username, password)
        if not login_success:
            logger.error("Failed to login for report retrieval")
            return web.json_response({
                "status": "error",
                "message": "Authentication failed"
            }, status=401)
        
        # Make initial request to the report endpoint
        report_url = f"{SERVICE_URL}/analyse/Reports/analyseFile.asp?id={report_id}"
        logger.debug(f"Making report request to: {report_url}")
        
        # Follow up to 5 redirects to get the final report data
        redirect_count = 0
        max_redirects = 5
        current_url = report_url
        
        while redirect_count < max_redirects:
            response_text, success, error_response = await make_authenticated_request(
                session, current_url, "GET", None, username, password
            )
            
            if not success:
                return error_response
            
            # Check if this is the final response (not a redirect)
            # We need to make a direct request to check the status code
            async with session.get(current_url, headers=HEADERS) as response:
                logger.debug(f"Report request response status: {response.status}")
                
                # If we get the final data (not a redirect), break the loop
                if response.status != 302:
                    logger.info(f"Report retrieval completed successfully after {redirect_count} redirects")
                    
                    # Parse the report data
                    parsed_data = parse_report_data(response_text)
                    
                    # Create enhanced FHIR DiagnosticReport resource
                    fhir_report = {
                        "resourceType": "DiagnosticReport",
                        "id": report_id,
                        "meta": {
                            "lastUpdated": datetime.now().isoformat()
                        },
                        "status": "final",
                        "category": [
                            {
                                "coding": [
                                    {
                                        "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                                        "code": "RAD",
                                        "display": "Radiology"
                                    }
                                ]
                            }
                        ],
                        "code": {
                            "coding": [
                                {
                                    "system": f"http://{request.host}/fhir/CodeSystem/report-types",
                                    "code": "imaging-report",
                                    "display": "Imaging Report"
                                }
                            ],
                            "text": parsed_data.get("examination", "Imaging Report")
                        },
                        "subject": {
                            "reference": f"Patient/{parsed_data.get('patient_id', '')}"
                        }
                    }
                    
                    # Add effective date if available
                    if parsed_data.get("sample_datetime"):
                        fhir_report["effectiveDateTime"] = parsed_data["sample_datetime"]
                    
                    # Add performer if available
                    if parsed_data.get("examiner"):
                        fhir_report["performer"] = [
                            {
                                "display": parsed_data["examiner"]
                            }
                        ]
                    
                    # Add results if available
                    if parsed_data.get("reports"):
                        fhir_report["result"] = []
                        for i, report in enumerate(parsed_data["reports"]):
                            fhir_report["result"].append({
                                "reference": f"Observation/{report_id}-{i}"
                            })
                        
                        # Add conclusion from the first report result
                        if parsed_data["reports"]:
                            first_report = parsed_data["reports"][0]
                            if first_report.get("result"):
                                fhir_report["conclusion"] = first_report["result"]
                    
                    # Add media references placeholder
                    fhir_report["media"] = []
                    
                    return web.json_response(fhir_report)
                
                # Handle 302 redirect
                location = response.headers.get("Location")
                if not location:
                    logger.error("302 redirect without Location header")
                    return create_error_response("Redirect without location header", 500)
                
                # Construct the full URL for the redirect
                if location.startswith("/"):
                    # Relative path from root
                    current_url = f"http://192.168.3.230{location}"
                elif location.startswith("http"):
                    # Full URL
                    current_url = location
                else:
                    # Relative path from current directory
                    base_path = "/".join(current_url.split("/")[:-1])
                    current_url = f"{base_path}/{location}"
                
                logger.debug(f"Following redirect #{redirect_count + 1} to: {current_url}")
                redirect_count += 1
        
        # If we've exceeded the maximum redirects
        logger.error(f"Exceeded maximum redirects ({max_redirects}) while retrieving report")
        return create_error_response(f"Exceeded maximum redirects ({max_redirects})", 500)
            
    except Exception as e:
        logger.error(f"Report retrieval failed with exception: {e}")
        return web.json_response({
            "status": "error",
            "message": str(e)
        }, status=500)

async def init_app():
    """Initialize the web application.
    
    Sets up routes and application lifecycle handlers.
    
    Returns:
        Configured web application
    """
    logger.info("Initializing web application")
    app = web.Application()
    app.router.add_get('/', root_handler)
    # FHIR-compatible endpoints
    app.router.add_get('/fhir/Patient', fhir_patient_search)
    app.router.add_get('/fhir/Patient/{id}', fhir_patient_read)
    app.router.add_get('/fhir/DiagnosticReport', fhir_diagnostic_report_read)
    app.router.add_get('/fhir/Encounter', fhir_encounter_read)
    app.router.add_get('/fhir/Observation', fhir_observation_search)
    app.router.add_get('/fhir/Observation/{id}', fhir_observation_read)
    app.router.add_get('/fhir/ValueSet/cnp', fhir_cnp_validate)
    app.router.add_post('/fhir/login', fhir_login)
    app.router.add_post('/fhir/md2html', fhir_markdown_to_html)
    app.router.add_get('/fhir/CodeSystem/analysis-types', fhir_analysis_types)
    app.router.add_get('/fhir/spec', fhir_specification)
    app.router.add_static('/static/', path='static', name='static')
    
    # Setup startup and cleanup
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    
    return app

async def on_startup(app):
    """Handle application startup.
    
    Initializes the HTTP session.
    
    Args:
        app: The web application
    """
    logger.info("Application startup")
    await get_session()

async def on_cleanup(app):
    """Handle application cleanup.
    
    Closes the HTTP session.
    
    Args:
        app: The web application
    """
    logger.info("Application cleanup")
    global session
    if session and not session.closed:
        logger.debug("Closing aiohttp ClientSession")
        await session.close()

if __name__ == "__main__":
    logger.info(f"Starting HippoBridge server on {HOST}:{PORT}")
    app = init_app()
    web.run_app(app, host=HOST, port=PORT)
