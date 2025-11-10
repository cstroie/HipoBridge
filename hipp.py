#!/usr/bin/env python3
import os
import asyncio
import aiohttp
from aiohttp import web
from typing import Dict, Any, Optional, List
import json
import logging
import re
from bs4 import BeautifulSoup
import html
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('hipp')

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
    """Handle requests to the root endpoint.
    
    Returns a web page with a CNP input form and analysis functionality.
    
    Args:
        request: The incoming HTTP request
        
    Returns:
        web.Response: HTML response with the web interface
    """
    logger.info("Root endpoint accessed")
    
    # Serve the external HTML file
    with open('static/main.html', 'r') as f:
        html_content = f.read()
    
    return web.Response(text=html_content, content_type='text/html')

def is_login_page(content: str) -> bool:
    """Detect if the provided content is a login page.
    
    Checks for specific text patterns that indicate we're on the login page.
    
    Args:
        content (str): HTML content to check
        
    Returns:
        bool: True if content appears to be a login page, False otherwise
    """
    is_login = "RECUPERARE PAROLA" in content and "Username" in content and "Password" in content
    if is_login:
        logger.debug("Detected login page")
    return is_login

async def login_if_needed(username: str = None, password: str = None) -> bool:
    """Attempt to login to the Hipocrate service if needed.
    
    Checks if we're currently on the login page, and if so, performs login
    using the provided or environment credentials.
    
    Args:
        username (str, optional): Username for login. Defaults to environment variable.
        password (str, optional): Password for login. Defaults to environment variable.
        
    Returns:
        bool: True if login was successful or not needed, False otherwise
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
                cookies = session.cookie_jar.filter_cookies(SERVICE_URL)
                logger.debug(f"Session cookies after login: {len(cookies)} cookies")
        
        # Check if login was successful (redirect to main.asp or not on login page)
        if login_response.status == 302 and "main.asp" in login_response.headers.get("Location", ""):
            logger.info("Login successful - redirected to main.asp")
            return True
        elif not is_login_page(response_text):
            logger.info("Login successful - not on login page")
            return True
        else:
            logger.warning("Login failed - still on login page")
        return False
    except Exception as e:
        logger.error(f"Login failed with exception: {e}")
        return False


async def login_handler(request):
    """Handle explicit login requests.
    
    Performs login to the Hipocrate service using credentials provided in the request body.
    
    Args:
        request: The incoming HTTP request with JSON body containing username and password
        
    Returns:
        web.Response: JSON response indicating login success or failure
    """
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

async def make_authenticated_request(session, url, method="GET", data=None, username=None, password=None):
    """Make an authenticated request to the Hipocrate service with automatic login handling.
    
    Args:
        session: The aiohttp session to use
        url (str): The URL to request
        method (str): HTTP method ("GET" or "POST")
        data (dict, optional): Data to send with POST requests
        username (str, optional): Username for login if needed
        password (str, optional): Password for login if needed
        
    Returns:
        tuple: (response_text, success, error_response) where success is boolean
    """
    try:
        # Log current cookies before request
        if session.cookie_jar:
            cookies = session.cookie_jar.filter_cookies(SERVICE_URL)
            logger.debug(f"Using {len(cookies)} cookies for request to {url}")
        
        # First ensure we're logged in
        login_success = await login_if_needed(username, password)
        if not login_success:
            logger.error(f"Failed to login for request to {url}")
            return None, False, web.json_response({
                "status": "error",
                "message": "Authentication failed"
            }, status=401)
        
        # Make the request
        if method == "GET":
            logger.debug(f"Making GET request to: {url}")
            async with session.get(url, headers=HEADERS) as response:
                response_text = await _handle_response_encoding(response)
                logger.debug(f"GET response status: {response.status}")
        else:  # POST
            logger.debug(f"Making POST request to: {url}")
            async with session.post(url, data=data, headers=HEADERS) as response:
                response_text = await _handle_response_encoding(response)
                logger.debug(f"POST response status: {response.status}")
        
        # Check if we got redirected to login page (session expired)
        if is_login_page(response_text):
            logger.warning(f"Session expired during request to {url}, attempting re-login")
            login_success = await login_if_needed(username, password)
            if login_success:
                # Retry the request
                if method == "GET":
                    async with session.get(url, headers=HEADERS) as retry_response:
                        response_text = await _handle_response_encoding(retry_response)
                        logger.debug(f"Retry GET response status: {retry_response.status}")
                else:  # POST
                    async with session.post(url, data=data, headers=HEADERS) as retry_response:
                        response_text = await _handle_response_encoding(retry_response)
                        logger.debug(f"Retry POST response status: {retry_response.status}")
                
                if is_login_page(response_text):
                    logger.error("Login failed after retry")
                    return None, False, web.json_response({
                        "status": "error",
                        "message": "Authentication failed after retry"
                    }, status=401)
            else:
                logger.error("Re-login failed")
                return None, False, web.json_response({
                    "status": "error",
                    "message": "Authentication failed"
                }, status=401)
        
        return response_text, True, None
    except Exception as e:
        logger.error(f"Request to {url} failed with exception: {e}")
        return None, False, web.json_response({
            "status": "error",
            "message": str(e)
        }, status=500)

async def _handle_response_encoding(response):
    """Handle response encoding for the Hipocrate service.
    
    Args:
        response: The aiohttp response object
        
    Returns:
        str: Decoded response text
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

async def patient_search_handler(request):
    """Search for patients by name or other criteria.
    
    Performs a patient search on the Hipocrate service using the provided search term.
    Can return either a single patient result or multiple patient results.
    If the search term ends with *, it's treated as a partial CNP search.
    
    Args:
        request: The incoming HTTP request with 'q' query parameter for search term
                 and optional X-Username and X-Password headers for authentication
        
    Returns:
        web.Response: JSON response with search results or error information
    """
    logger.info("GET /api/patient/search endpoint accessed")
    
    # Get credentials from request headers (optional)
    username = request.headers.get("X-Username")
    password = request.headers.get("X-Password")
    
    # Get search parameter from query string
    search_term = request.query.get('q', '')
    
    if not search_term:
        logger.warning("No search term provided")
        return web.json_response({
            "status": "error",
            "message": "Search term is required"
        }, status=400)
    
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
            "strDescription": actual_search_term if search_type in ["name", "code"] else "",
            "strLastName": "",
            "strFirstName": "",
            "strCodePres": "",
            "strCNP": cnp_value if search_type in ["cnp", "partial_cnp"] else "",
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
        
        response_text, success, error_response = await make_authenticated_request(
            session, search_url, "POST", search_data, username, password
        )
        
        if not success:
            return error_response
        
        logger.info("Patient search completed successfully")
        
        # Try to parse as single patient page first
        single_patient_data = parse_single_patient_data(response_text)
        if single_patient_data and single_patient_data.get("patient_name"):
            return web.json_response({
                "status": "success",
                "type": "single_patient",
                "data": single_patient_data
            })
        
        # Try to parse as multiple patients page
        multiple_patients_data = parse_multiple_patients_data(response_text)
        if multiple_patients_data:
            return web.json_response({
                "status": "success",
                "type": "multiple_patients",
                "data": multiple_patients_data
            })
        
        # If neither parser worked, return raw data
        return web.json_response({
            "status": "success",
            "type": "raw",
            "data": response_text
        })
            
    except Exception as e:
        logger.error(f"Patient search failed with exception: {e}")
        return web.json_response({
            "status": "error",
            "message": str(e)
        }, status=500)

def html_to_markdown(html_content: str) -> str:
    """Convert HTML content to clean markdown text.
    
    Processes HTML content by removing unnecessary tags, converting formatting
    elements to markdown syntax, and normalizing whitespace.
    
    Args:
        html_content (str): HTML content to convert
        
    Returns:
        str: Clean markdown text
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
        soup (BeautifulSoup): Parsed HTML content
        label_regex (str): Regular expression pattern to match label text
        
    Returns:
        str: Content of the textarea converted to markdown, or empty string if not found
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
        html_content (str): HTML content of the report
        
    Returns:
        Dict[str, Any]: Dictionary containing parsed report data
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
            "patient_id": "",
            "patient_code": "",
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
        
        # Extract patient ID (CNP)
        cnp_match = re.search(r'C\.N\.P:\s*([^\n\r<>&]+)', text_content, re.IGNORECASE)
        if cnp_match:
            report_data["patient_id"] = re.sub(r'\s+', ' ', cnp_match.group(1).strip())
        
        # Extract patient code
        code_match = re.search(r'Cod pacient:\s*([^\n\r<>&]+)', text_content, re.IGNORECASE)
        if code_match:
            report_data["patient_code"] = re.sub(r'\s+', ' ', code_match.group(1).strip())
        
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

def parse_single_patient_data(html_content: str) -> Dict[str, Any]:
    """Parse HTML content for a single patient page and extract patient data.
    
    Extracts patient name, ID, code, and associated presentation/checkin/checkout IDs
    from a single patient page HTML content.
    
    Args:
        html_content (str): HTML content of the single patient page
        
    Returns:
        Dict[str, Any]: Dictionary containing parsed patient data, or empty dict if not a patient page
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Check if this is a single patient page by looking for 'Date pasaportale' in title
        title = soup.find('title')
        if not title or 'Date pasaportale' not in title.get_text():
            return {}
        
        # Extract patient name from div with id "div_navbar"
        navbar_div = soup.find('div', id='div_navbar')
        patient_name = ""
        if navbar_div:
            patient_name = navbar_div.get_text().strip()
        
        # Extract patient ID (CNP) from text input after 'CNP:'
        patient_id = ""
        cnp_labels = soup.find_all(string=re.compile(r'CNP\s*:', re.IGNORECASE))
        for label in cnp_labels:
            # Find the parent element and then look for the next input
            parent = label.parent
            if parent:
                input_field = parent.find_next('input', type='text')
                if input_field:
                    patient_id = input_field.get('value', '').strip()
                    break
        
        # Extract patient code from hidden input with id "hdnCodeID"
        patient_code = ""
        code_input = soup.find('input', id='hdnCodeID', type='hidden')
        if code_input:
            patient_code = code_input.get('value', '').strip()
        
        # Extract presentations
        presentations = []
        presentation_links = soup.find_all('a', href=re.compile(r'../files/presentation\.asp\?id='))
        for link in presentation_links:
            href = link.get('href', '')
            id_match = re.search(r'id=([^&"]+)', href)
            if id_match:
                presentations.append(id_match.group(1))
        
        # Extract checkins
        checkins = []
        checkin_links = soup.find_all('a', href=re.compile(r'../files/checkin\.asp\?id='))
        for link in checkin_links:
            href = link.get('href', '')
            id_match = re.search(r'id=([^&"]+)', href)
            if id_match:
                checkins.append(id_match.group(1))
        
        # Extract checkouts
        checkouts = []
        checkout_links = soup.find_all('a', href=re.compile(r'../files/checkout\.asp\?id='))
        for link in checkout_links:
            href = link.get('href', '')
            id_match = re.search(r'id=([^&"]+)', href)
            if id_match:
                checkouts.append(id_match.group(1))
        
        return {
            "patient_name": patient_name,
            "patient_id": patient_id,
            "patient_code": patient_code,
            "presentations": presentations,
            "checkins": checkins,
            "checkouts": checkouts
        }
    except Exception as e:
        logger.error(f"Error parsing single patient data: {e}")
        return {}

def parse_multiple_patients_data(html_content: str) -> List[Dict[str, Any]]:
    """Parse HTML content for multiple patient search results and extract patient data.
    
    Extracts patient names, CNP, and codes from search results page with multiple patients.
    
    Args:
        html_content (str): HTML content of the search results page
        
    Returns:
        List[Dict[str, Any]]: List of dictionaries containing patient data (name, CNP, code only)
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Check if this is a search results page by looking for 'Fisier' in title
        title = soup.find('title')
        if not title or 'Fisier' not in title.get_text():
            return []
        
        patients = []
        
        # Find all table rows
        rows = soup.find_all('tr')
        
        for row in rows:
            # Look for the patient code link
            code_link = row.find('a', href=re.compile(r"javascript:Edit\('([^']+)'\);"))
            if not code_link:
                continue
                
            # Extract patient code
            code_href = code_link.get('href')
            code_match = re.search(r"javascript:Edit\('([^']+)'\);", code_href)
            if not code_match:
                continue
            patient_code = code_match.group(1)
            
            # Look for the patient name link (next link in the row)
            name_links = row.find_all('a')
            patient_name = ""
            for name_link in name_links:
                if name_link != code_link:
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
            
            # Only add patient if we have at least a name or code
            if patient_name or patient_code:
                patient_data = {
                    "patient_name": patient_name,
                    "patient_id": patient_cnp,  # CNP
                    "patient_code": patient_code
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
        html_content (str): HTML content of the checkout page
        
    Returns:
        Dict[str, Any]: Dictionary containing parsed checkout data
    """
    import re
    from bs4 import BeautifulSoup
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Initialize result dictionary
        checkout_data = {
            "patient_name": "",
            "patient_id": "",
            "patient_code": "",
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
        
        # Extract patient code (Cod pacient)
        code_elements = soup.find_all('td', string=re.compile(r'Cod pacient\s*:', re.IGNORECASE))
        for code_element in code_elements:
            next_td = code_element.find_next('td')
            if next_td:
                checkout_data["patient_code"] = next_td.get_text().strip()
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

async def patient_handler(request):
    """Retrieve patient information by ID.
    
    Gets patient information from the Hipocrate service and extracts
    associated checkin and checkout IDs.
    
    Args:
        request: The incoming HTTP request with 'id' query parameter for patient ID
                 and optional X-Username and X-Password headers for authentication
        
    Returns:
        web.Response: JSON response with patient data or error information
    """
    logger.info("GET /api/patient endpoint accessed")
    
    # Get credentials from request headers (optional)
    username = request.headers.get("X-Username")
    password = request.headers.get("X-Password")
    
    # Get patient ID from query string
    patient_id = request.query.get('id')
    
    if not patient_id:
        logger.warning("No patient ID provided")
        return web.json_response({
            "status": "error",
            "message": "Patient ID is required"
        }, status=400)
    
    logger.info(f"Retrieving patient with ID: {patient_id}")
    
    try:
        session = await get_session()
        
        # Make request to the patient endpoint
        patient_url = f"{SERVICE_URL}/Pacient/edit.asp?id={patient_id}"
        
        response_text, success, error_response = await make_authenticated_request(
            session, patient_url, "GET", None, username, password
        )
        
        if not success:
            return error_response
        
        # Parse the patient data to extract checkout and checkin IDs
        checkout_ids = []
        checkin_ids = []
        
        try:
            from bs4 import BeautifulSoup
            import re
            
            soup = BeautifulSoup(response_text, 'html.parser')
            
            # Extract checkout IDs
            checkout_links = soup.find_all('a', href=re.compile(r'../files/checkout\.asp\?id='))
            for link in checkout_links:
                href = link.get('href', '')
                id_match = re.search(r'id=([^&"]+)', href)
                if id_match:
                    checkout_ids.append(id_match.group(1))
            
            # Extract checkin IDs
            checkin_links = soup.find_all('a', href=re.compile(r'../files/checkin\.asp\?id='))
            for link in checkin_links:
                href = link.get('href', '')
                id_match = re.search(r'id=([^&"]+)', href)
                if id_match:
                    checkin_ids.append(id_match.group(1))
            
            logger.info(f"Found {len(checkout_ids)} checkout IDs and {len(checkin_ids)} checkin IDs")
            
        except Exception as e:
            logger.error(f"Error parsing patient data: {e}")
        
        logger.info("Patient retrieval completed successfully")
        return web.json_response({
            "status": "success",
            "checkout_ids": checkout_ids,
            "checkin_ids": checkin_ids
        })
            
    except Exception as e:
        logger.error(f"Patient retrieval failed with exception: {e}")
        return web.json_response({
            "status": "error",
            "message": str(e)
        }, status=500)

async def checkout_handler(request):
    """Retrieve checkout information by ID.
    
    Gets checkout information from the Hipocrate service and parses
    the medical data into structured format.
    
    Args:
        request: The incoming HTTP request with 'id' query parameter for checkout ID
                 and optional X-Username and X-Password headers for authentication
        
    Returns:
        web.Response: JSON response with checkout data or error information
    """
    logger.info("GET /api/checkout endpoint accessed")
    
    # Get credentials from request headers (optional)
    username = request.headers.get("X-Username")
    password = request.headers.get("X-Password")
    
    # Get checkout ID from query string
    checkout_id = request.query.get('id')
    
    if not checkout_id:
        logger.warning("No checkout ID provided")
        return web.json_response({
            "status": "error",
            "message": "Checkout ID is required"
        }, status=400)
    
    logger.info(f"Retrieving checkout with ID: {checkout_id}")
    
    try:
        session = await get_session()
        
        # Make request to the checkout endpoint
        checkout_url = f"{SERVICE_URL}/files/checkout.asp?id={checkout_id}"
        
        response_text, success, error_response = await make_authenticated_request(
            session, checkout_url, "GET", None, username, password
        )
        
        if not success:
            return error_response
        
        logger.info("Checkout retrieval completed successfully")
        # Parse the checkout data
        parsed_data = parse_checkout_data(response_text)
        
        result = {"status": "success"}
        result.update(parsed_data)
        return web.json_response(result)
            
    except Exception as e:
        logger.error(f"Checkout retrieval failed with exception: {e}")
        return web.json_response({
            "status": "error",
            "message": str(e)
        }, status=500)

def parse_analyses_data(html_content: str) -> Dict[str, Any]:
    """Parse HTML analyses content and extract report IDs, analysis types, and patient name.
    
    Extracts patient name and list of analyses with their types and report IDs
    from the analyses HTML page.
    
    Args:
        html_content (str): HTML content of the analyses page
        
    Returns:
        Dict[str, Any]: Dictionary containing patient name and list of analyses
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Initialize result
        result = {
            "patient_name": "",
            "analyses": []
        }
        
        # Extract patient name from the link pattern
        patient_link = soup.find('a', href=re.compile(r'../Pacient/edit\.asp\?id=\d+'))
        if patient_link:
            result["patient_name"] = patient_link.get_text().strip()
        
        # Find all links to analysis reports
        report_links = soup.find_all('a', href=re.compile(r'../analyse/Reports/analyseFile\.asp\?id=\d+'))
        
        for link in report_links:
            # Extract report ID
            href = link.get('href', '')
            id_match = re.search(r'id=(\d+)', href)
            if not id_match:
                continue
            
            report_id = id_match.group(1)
            
            # Find the parent table row
            parent_row = link.find_parent('tr')
            if not parent_row:
                # If no parent row, just add the ID without type
                result["analyses"].append({
                    "report_id": report_id,
                    "type": "unknown"
                })
                continue
            
            # Look for the analysis type in the same row
            # The type is coded as 'XXXX-Radio', 'XXXX-lab', 'XXXX-IRM', etc.
            type_text = ""
            cells = parent_row.find_all('td')
            for cell in cells:
                cell_text = cell.get_text().strip()
                # Look for pattern like 'XXXX-Radio', 'XXXX-lab', etc.
                type_match = re.search(r'\d{4}-(\w+)', cell_text)
                if type_match:
                    type_text = type_match.group(1).lower()
                    break
            
            # If we didn't find the type in the standard format, try to infer from the text
            if not type_text:
                # Look for common type indicators in the row
                row_text = parent_row.get_text().lower()
                if 'radio' in row_text or 'radiologie' in row_text:
                    type_text = "radio"
                elif 'lab' in row_text or 'laborator' in row_text:
                    type_text = "lab"
                elif 'irm' in row_text:
                    type_text = "irm"
                elif 'ct' in row_text:
                    type_text = "ct"
                elif 'eco' in row_text or 'ecografie' in row_text:
                    type_text = "eco"
                else:
                    type_text = "unknown"
            
            result["analyses"].append({
                "report_id": report_id,
                "type": type_text
            })
        
        return result
    except Exception as e:
        logger.error(f"Error parsing analyses data: {e}")
        return {"patient_name": "", "analyses": []}

async def analyses_handler(request):
    """Retrieve all analyses for a patient by ID.
    
    Gets all analyses for a specific patient from the Hipocrate service
    and parses the data into structured format.
    
    Args:
        request: The incoming HTTP request with 'id' query parameter for patient ID
                 and optional X-Username and X-Password headers for authentication
        
    Returns:
        web.Response: JSON response with analyses data or error information
    """
    logger.info("GET /api/analyses endpoint accessed")
    
    # Get credentials from request headers (optional)
    username = request.headers.get("X-Username")
    password = request.headers.get("X-Password")
    
    # Get patient ID from query string
    patient_id = request.query.get('id')
    
    if not patient_id:
        logger.warning("No patient ID provided")
        return web.json_response({
            "status": "error",
            "message": "Patient ID is required"
        }, status=400)
    
    # Get optional parameters
    analysis_type = request.query.get('type')
    datetime_filter = request.query.get('dt')
    
    logger.info(f"Retrieving analyses for patient with ID: {patient_id}")
    
    try:
        session = await get_session()
        
        # Make request to the analyses endpoint
        analyses_url = f"{SERVICE_URL}/pacient/analyses.asp?type=PA&pacid={patient_id}"
        
        response_text, success, error_response = await make_authenticated_request(
            session, analyses_url, "GET", None, username, password
        )
        
        if not success:
            return error_response
        
        logger.info("Analyses retrieval completed successfully")
        # Parse the analyses data to extract report IDs, types, and patient name
        parsed_data = parse_analyses_data(response_text)
        
        # Filter analyses by type if specified
        analyses = parsed_data["analyses"]
        if analysis_type:
            analyses = [a for a in analyses if a["type"] == analysis_type]
        
        # Filter analyses by datetime if specified
        if datetime_filter and analyses:
            # For datetime filtering, we need to get report details to check dates
            filtered_analyses = []
            try:
                from datetime import datetime, timedelta
                
                # Parse the filter datetime
                filter_dt = datetime.fromisoformat(datetime_filter)
                # Define the time window (up to 6 hours later)
                max_dt = filter_dt + timedelta(hours=6)
                
                # Check each analysis
                for analysis in analyses:
                    # Get report details to extract datetime
                    report_url = f"{SERVICE_URL}/analyse/Reports/analyseFile.asp?id={analysis['report_id']}"
                    report_text, success, _ = await make_authenticated_request(
                        session, report_url, "GET", None, username, password
                    )
                    
                    if success:
                        # Parse report to get datetime
                        report_data = parse_report_data(report_text)
                        report_datetime_str = report_data.get("sample_datetime")
                        
                        if report_datetime_str:
                            # Try to parse the report datetime
                            try:
                                # Handle common date formats
                                if re.match(r'\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}', report_datetime_str):
                                    report_dt = datetime.strptime(report_datetime_str, '%d/%m/%Y %H:%M:%S')
                                elif re.match(r'\d{2}/\d{2}/\d{4}', report_datetime_str):
                                    report_dt = datetime.strptime(report_datetime_str, '%d/%m/%Y')
                                else:
                                    # Try ISO format
                                    report_dt = datetime.fromisoformat(report_datetime_str)
                                
                                # Check if report is within the time window
                                if filter_dt <= report_dt <= max_dt:
                                    filtered_analyses.append(analysis)
                            except ValueError:
                                # If we can't parse the datetime, include the analysis
                                filtered_analyses.append(analysis)
                        else:
                            # If no datetime in report, include the analysis
                            filtered_analyses.append(analysis)
                    else:
                        # If we can't get report details, include the analysis
                        filtered_analyses.append(analysis)
                
                analyses = filtered_analyses
            except Exception as e:
                logger.error(f"Error filtering analyses by datetime: {e}")
                # If datetime filtering fails, return unfiltered analyses
        
        return web.json_response({
            "status": "success",
            "patient_name": parsed_data["patient_name"],
            "analyses": analyses
        })
            
    except Exception as e:
        logger.error(f"Analyses retrieval failed with exception: {e}")
        return web.json_response({
            "status": "error",
            "message": str(e)
        }, status=500)

def validate_cnp(cnp: str) -> bool:
    """Validate a Romanian CNP (Personal Numerical Code).
    
    Checks if the provided string is a valid Romanian CNP by verifying:
    - Length (13 digits)
    - Gender digit (1-8)
    - Date components (year, month, day)
    - County code (1-52, excluding 47-50)
    - Control digit using checksum algorithm
    
    Args:
        cnp (str): The CNP to validate
        
    Returns:
        bool: True if CNP is valid, False otherwise
    """
    # Check if CNP is exactly 13 digits
    if not cnp or len(cnp) != 13 or not cnp.isdigit():
        return False
    
    # Extract components
    gender_digit = int(cnp[0])
    year = int(cnp[1:3])
    month = int(cnp[3:5])
    day = int(cnp[5:7])
    county_code = int(cnp[7:9])
    
    # Validate gender digit (1-8 are valid)
    if gender_digit < 1 or gender_digit > 8:
        return False
    
    # Validate month (1-12)
    if month < 1 or month > 12:
        return False
    
    # Validate day (1-31)
    if day < 1 or day > 31:
        return False
    
    # Validate county code (1-52, excluding 47-50, plus 70-79 for diaspora, 90-99 for special cases)
    if not ((1 <= county_code <= 52 and not (47 <= county_code <= 50)) or 
            (70 <= county_code <= 79) or 
            (90 <= county_code <= 99)):
        return False
    
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
        datetime(full_year, month, day)
    except ValueError:
        return False
    
    # Validate control digit using checksum
    weights = [2, 7, 9, 1, 4, 6, 3, 5, 8, 2, 7, 9]
    checksum = sum(int(cnp[i]) * weights[i] for i in range(12)) % 11
    control_digit = 1 if checksum == 10 else checksum
    
    return control_digit == int(cnp[12])

async def cnp_handler(request):
    """Validate a Romanian CNP (Personal Numerical Code).
    
    Validates a Romanian CNP using the internal validation algorithm.
    
    Args:
        request: The incoming HTTP request with 'id' query parameter for CNP
        
    Returns:
        web.Response: JSON response with validation result
    """
    logger.info("GET /api/cnp endpoint accessed")
    
    # Get CNP from query string
    cnp = request.query.get('id')
    
    if not cnp:
        logger.warning("No CNP provided")
        return web.json_response({
            "status": "error",
            "message": "CNP is required"
        }, status=400)
    
    logger.info(f"Validating CNP: {cnp}")
    
    # Validate CNP
    is_valid = validate_cnp(cnp)
    
    return web.json_response({
        "status": "success",
        "cnp": cnp,
        "valid": is_valid
    })

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
        markdown_text (str): Markdown text to convert
        
    Returns:
        str: HTML representation of the markdown
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

async def markdown_handler(request):
    """Convert markdown text to HTML.
    
    Takes markdown text and converts it to basic HTML.
    
    Args:
        request: The incoming HTTP request with 'text' query parameter
        
    Returns:
        web.Response: JSON response with HTML content
    """
    logger.info("GET /api/markdown endpoint accessed")
    
    # Get markdown text from query string
    markdown_text = request.query.get('text', '')
    
    try:
        html_content = markdown_to_html(markdown_text)
        
        return web.json_response({
            "status": "success",
            "html": html_content
        })
    except Exception as e:
        logger.error(f"Markdown conversion failed: {e}")
        return web.json_response({
            "status": "error",
            "message": str(e)
        }, status=500)

async def spec_handler(request):
    """Serve the OpenAPI specification.
    
    Returns the OpenAPI specification in JSON format for API documentation.
    
    Args:
        request: The incoming HTTP request
        
    Returns:
        web.Response: JSON response with OpenAPI specification
    """
    logger.info("GET /api/spec endpoint accessed")
    
    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "Hipocrate Patient Analyzer API",
            "description": "API for accessing patient data from the Hipocrate medical system",
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
            "/api/login": {
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
            "/api/markdown": {
                "get": {
                    "summary": "Convert markdown to HTML",
                    "description": "Convert simple markdown text to basic HTML",
                    "parameters": [
                        {
                            "name": "text",
                            "in": "query",
                            "required": False,
                            "description": "Markdown text to convert",
                            "schema": {
                                "type": "string"
                            }
                        }
                    ],
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
            "/api/patients/search": {
                "get": {
                    "summary": "Search for patients",
                    "description": "Search for patients by name or CNP",
                    "parameters": [
                        {
                            "name": "q",
                            "in": "query",
                            "required": True,
                            "description": "Search term (patient name or CNP)",
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
                            "description": "Search results",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "example": "success"
                                            },
                                            "type": {
                                                "type": "string",
                                                "example": "single_patient"
                                            },
                                            "data": {
                                                "type": "object"
                                            }
                                        }
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
            "/api/patients": {
                "get": {
                    "summary": "Get patient information",
                    "description": "Retrieve patient information by ID",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "query",
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
                            "description": "Patient information",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "example": "success"
                                            },
                                            "checkout_ids": {
                                                "type": "array",
                                                "items": {
                                                    "type": "string"
                                                }
                                            },
                                            "checkin_ids": {
                                                "type": "array",
                                                "items": {
                                                    "type": "string"
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
            "/api/analyses": {
                "get": {
                    "summary": "Get patient analyses",
                    "description": "Retrieve all analyses for a patient with optional filtering by type and datetime",
                    "parameters": [
                        {
                            "name": "id",
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
                            "description": "Analysis type to filter by (e.g., radio, ct, irm, eco, lab)",
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
                            "description": "Patient analyses",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "example": "success"
                                            },
                                            "patient_name": {
                                                "type": "string"
                                            },
                                            "analyses": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "report_id": {
                                                            "type": "string"
                                                        },
                                                        "type": {
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
            "/api/reports": {
                "get": {
                    "summary": "Get analysis report",
                    "description": "Retrieve an analysis report by ID",
                    "parameters": [
                        {
                            "name": "id",
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
                            "description": "Analysis report",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "example": "success"
                                            },
                                            "patient_name": {
                                                "type": "string"
                                            },
                                            "age": {
                                                "type": "string"
                                            },
                                            "gender": {
                                                "type": "string"
                                            },
                                            "patient_id": {
                                                "type": "string"
                                            },
                                            "patient_code": {
                                                "type": "string"
                                            },
                                            "sample_datetime": {
                                                "type": "string"
                                            },
                                            "examination": {
                                                "type": "string"
                                            },
                                            "reports": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object"
                                                }
                                            },
                                            "examiner": {
                                                "type": "string"
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
            "/api/checkouts": {
                "get": {
                    "summary": "Get checkout information",
                    "description": "Retrieve checkout information by ID",
                    "parameters": [
                        {
                            "name": "id",
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
                            "description": "Checkout information",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {
                                                "type": "string",
                                                "example": "success"
                                            },
                                            "patient_name": {
                                                "type": "string"
                                            },
                                            "patient_id": {
                                                "type": "string"
                                            },
                                            "patient_code": {
                                                "type": "string"
                                            },
                                            "admission_diagnostic": {
                                                "type": "string"
                                            },
                                            "epicrisis": {
                                                "type": "string"
                                            },
                                            "diagnostic": {
                                                "type": "string"
                                            },
                                            "surgery": {
                                                "type": "string"
                                            },
                                            "recommendations": {
                                                "type": "string"
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
            "/api/cnp": {
                "get": {
                    "summary": "Validate CNP",
                    "description": "Validate a Romanian Personal Numerical Code (CNP)",
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
                            "description": "CNP validation result",
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
            }
        }
    }
    
    return web.json_response(spec)

async def report_handler(request):
    """Retrieve a report by ID, following redirect chains.
    
    Gets a report from the Hipocrate service, following any redirects to
    retrieve the final report data, then parses it into structured format.
    
    Args:
        request: The incoming HTTP request with 'id' query parameter for report ID
                 and optional X-Username and X-Password headers for authentication
        
    Returns:
        web.Response: JSON response with report data or error information
    """
    logger.info("GET /api/report endpoint accessed")
    
    # Get credentials from request headers (optional)
    username = request.headers.get("X-Username")
    password = request.headers.get("X-Password")
    
    # Get report ID from query string
    report_id = request.query.get('id')
    
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
        logger.debug(f"Making initial report request to: {report_url}")
        
        # Follow up to 5 redirects to get the final report data
        redirect_count = 0
        max_redirects = 5
        current_url = report_url
        
        while redirect_count < max_redirects:
            response_text, success, error_response = await make_authenticated_request(
                session, current_url, "GET", None, username, password
            )
            
            if not success:
                # If authentication failed during redirect, return the error
                if redirect_count > 0:
                    logger.info(f"Report retrieval completed successfully after {redirect_count} redirects")
                    # Parse the report data we have so far
                    parsed_data = parse_report_data(response_text)
                    result = {"status": "success", "redirects_followed": redirect_count}
                    result.update(parsed_data)
                    return web.json_response(result)
                else:
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
                    result = {"status": "success", "redirects_followed": redirect_count}
                    result.update(parsed_data)
                    return web.json_response(result)
                
                # Handle 302 redirect
                location = response.headers.get("Location")
                if not location:
                    logger.error("302 redirect without Location header")
                    return web.json_response({
                        "status": "error",
                        "message": "Redirect without location header"
                    }, status=500)
                
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
        return web.json_response({
            "status": "error",
            "message": f"Exceeded maximum redirects ({max_redirects})"
        }, status=500)
            
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
        web.Application: Configured web application
    """
    logger.info("Initializing web application")
    app = web.Application()
    app.router.add_get('/', root_handler)
    app.router.add_get('/api/patients/search', patient_search_handler)
    app.router.add_get('/api/patients', patient_handler)
    app.router.add_get('/api/analyses', analyses_handler)
    app.router.add_get('/api/reports', report_handler)
    app.router.add_get('/api/checkouts', checkout_handler)
    app.router.add_get('/api/cnp', cnp_handler)
    app.router.add_post('/api/login', login_handler)
    app.router.add_get('/api/markdown', markdown_handler)
    app.router.add_get('/api/spec', spec_handler)
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
    logger.info(f"Starting web server on port {PORT}")
    app = init_app()
    web.run_app(app, host="0.0.0.0", port=PORT)
