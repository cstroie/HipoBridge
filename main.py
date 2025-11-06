#!/usr/bin/env python3
import os
import asyncio
import aiohttp
from aiohttp import web
from typing import Dict, Any, Optional
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
    
    # Get search parameter from query string
    search_term = request.query.get('q', '')
    
    if not search_term:
        logger.warning("No search term provided")
        return web.json_response({
            "status": "error",
            "message": "Search term is required"
        }, status=400)
    
    logger.info(f"Searching for patients with term: {search_term}")
    
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
        
        # Prepare full search data as captured in the POST request
        search_data = {
            "hdnSearchType": "1",
            "pageNo": "1",
            "strDescription": search_term,
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
            "btnCODQR": "IMPORTA+COD+QR",
            "btnCODQRClear": "STERGE+COD+QR",
            "hdnQRSave": "",
            "IdQR": ""
        }
        
        # Make search request to the patient search page
        search_url = f"{SERVICE_URL}/files/search.asp?what=PA"
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
    """Convert HTML content to clean markdown"""
    
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
        
        # Bold
        for b in soup.find_all(['b', 'strong']):
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
    """Get content of first textarea after a label matching the given regex"""
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
    """Parse HTML report content and extract structured data"""
    
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
                    result_content = html_to_markdown(str(result_div))
                
                # Add to reports list
                report_data["reports"].append({
                    "investigation": investigation_name,
                    "result": result_content
                })
            except Exception as e:
                logger.error(f"Error parsing individual report: {e}")
                continue
        
        # Extract examiner (MEDIC,)
        examiner_match = re.search(r'MEDIC,\s*([^\n\r<>&]+)', text_content, re.IGNORECASE)
        if examiner_match:
            report_data["examiner"] = re.sub(r'\s+', ' ', examiner_match.group(1).strip())
        
        return report_data
    except Exception as e:
        logger.error(f"Error parsing report data: {e}")
        return {}

def parse_single_patient_data(html_content: str) -> Dict[str, Any]:
    """Parse HTML content for a single patient page and extract patient data"""
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
        
        return {
            "patient_name": patient_name
        }
    except Exception as e:
        logger.error(f"Error parsing single patient data: {e}")
        return {}

def parse_multiple_patients_data(html_content: str) -> List[Dict[str, Any]]:
    """Parse HTML content for multiple patient search results and extract patient data"""
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
            for name_link in name_links:
                if name_link != code_link:
                    # Extract patient name
                    # Remove font tags and formatting
                    name_text = name_link.get_text()
                    # Clean up the name (remove extra spaces, normalize)
                    patient_name = re.sub(r'\s+', ' ', name_text.strip())
                    
                    if patient_name:
                        patients.append({
                            "patient_code": patient_code,
                            "patient_name": patient_name
                        })
                    break
        
        return patients
    except Exception as e:
        logger.error(f"Error parsing multiple patients data: {e}")
        return []

def parse_checkout_data(html_content: str) -> Dict[str, Any]:
    """Parse HTML checkout content and extract structured data"""
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
    """Retrieve patient information by ID"""
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
        
        # Log current cookies before request
        if session.cookie_jar:
            cookies = session.cookie_jar.filter_cookies(SERVICE_URL)
            logger.debug(f"Using {len(cookies)} cookies for patient request")
        
        # First ensure we're logged in
        login_success = await login_if_needed(username, password)
        if not login_success:
            logger.error("Failed to login for patient retrieval")
            return web.json_response({
                "status": "error",
                "message": "Authentication failed"
            }, status=401)
        
        # Make request to the patient endpoint
        patient_url = f"{SERVICE_URL}/Pacient/edit.asp?id={patient_id}"
        logger.debug(f"Making patient request to: {patient_url}")
        
        async with session.get(patient_url, headers=HEADERS) as response:
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
            
            logger.debug(f"Patient response status: {response.status}")
            
            # Check if we got redirected to login page (session expired)
            if is_login_page(response_text):
                logger.warning("Session expired during patient retrieval, attempting re-login")
                login_success = await login_if_needed(username, password)
                if login_success:
                    # Retry the request
                    async with session.get(patient_url, headers=HEADERS) as retry_response:
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
                        logger.debug(f"Retry patient response status: {retry_response.status}")
                        
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
    """Retrieve checkout information by ID"""
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
        
        # Log current cookies before request
        if session.cookie_jar:
            cookies = session.cookie_jar.filter_cookies(SERVICE_URL)
            logger.debug(f"Using {len(cookies)} cookies for checkout request")
        
        # First ensure we're logged in
        login_success = await login_if_needed(username, password)
        if not login_success:
            logger.error("Failed to login for checkout retrieval")
            return web.json_response({
                "status": "error",
                "message": "Authentication failed"
            }, status=401)
        
        # Make request to the checkout endpoint
        checkout_url = f"{SERVICE_URL}/files/checkout.asp?id={checkout_id}"
        logger.debug(f"Making checkout request to: {checkout_url}")
        
        async with session.get(checkout_url, headers=HEADERS) as response:
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
            
            logger.debug(f"Checkout response status: {response.status}")
            
            # Check if we got redirected to login page (session expired)
            if is_login_page(response_text):
                logger.warning("Session expired during checkout retrieval, attempting re-login")
                login_success = await login_if_needed(username, password)
                if login_success:
                    # Retry the request
                    async with session.get(checkout_url, headers=HEADERS) as retry_response:
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
                        logger.debug(f"Retry checkout response status: {retry_response.status}")
                        
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

async def report_handler(request):
    """Retrieve a report by ID, following redirect chains"""
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
        
        # Log current cookies before request
        if session.cookie_jar:
            cookies = session.cookie_jar.filter_cookies(SERVICE_URL)
            logger.debug(f"Using {len(cookies)} cookies for report request")
        
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
            async with session.get(current_url, headers=HEADERS) as response:
                logger.debug(f"Report request response status: {response.status}")
                
                # If we get the final data (not a redirect), break the loop
                if response.status != 302:
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
    logger.info("Initializing web application")
    app = web.Application()
    app.router.add_get('/', root_handler)
    app.router.add_get('/api/service', service_get_handler)
    app.router.add_post('/api/service', service_post_handler)
    app.router.add_get('/api/patient/search', patient_search_handler)
    app.router.add_get('/api/patient', patient_handler)
    app.router.add_get('/api/report', report_handler)
    app.router.add_get('/api/checkout', checkout_handler)
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
