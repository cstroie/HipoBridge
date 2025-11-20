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
from aiohttp import web, BasicAuth
from yarl import URL
from typing import Dict, Any, Optional, List
import json
import logging
import re
from bs4 import BeautifulSoup, Comment
import html
from datetime import datetime, timedelta
import configparser
import base64

# Import FHIR classes
from fhir import ServiceRequest as FHIRServiceRequest, CodeableConcept, Coding, Reference, CodeableReference, Condition, Patient as FHIRPatient


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


class URLCache:
    """Simple in-memory cache for HTTP responses with LRU eviction and timeout."""

    def __init__(self, max_size: int = 100, timeout: int = 600):
        """Initialize the cache.

        Args:
            max_size: Maximum number of entries to cache
            timeout: Cache timeout in seconds (default: 10 minutes)
        """
        self.max_size = max_size
        self.timeout = timeout
        self.cache: Dict[str, str] = {}
        self.timestamps: Dict[str, datetime] = {}

    def get(self, url: str) -> Optional[str]:
        """Get cached response for URL if exists and not expired.

        Args:
            url: URL to lookup

        Returns:
            Cached response text or None if not found or expired
        """
        if url not in self.cache:
            return None

        # Check if cache entry is still valid
        if url in self.timestamps:
            cache_age = (datetime.now() - self.timestamps[url]).total_seconds()
            if cache_age >= self.timeout:
                # Cache entry expired, remove it
                del self.cache[url]
                del self.timestamps[url]
                logger.debug(f"Expired cache entry removed for: {url}")
                return None
        # Return cached response
        logger.debug(f"Using cached response for: {url} (age: {(datetime.now() - self.timestamps[url]).total_seconds():.1f}s)")
        return self.cache[url]

    def put(self, url: str, response_text: str) -> None:
        """Add response to cache, evicting oldest entry if needed.

        Args:
            url: URL key
            response_text: Response text to cache
        """
        # If cache is at max size, remove the oldest entry
        if len(self.cache) >= self.max_size:
            # Remove the first (oldest) entry
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            if oldest_key in self.timestamps:
                del self.timestamps[oldest_key]
        # Add the new entry with timestamp
        self.cache[url] = response_text
        self.timestamps[url] = datetime.now()
        logger.debug(f"Cached response for: {url}")

    def remove(self, url: str) -> None:
        """Remove cache entries.

        Args:
            url: Specific URL to clear from cache, or None to clear all
        """
        if url:
            if url in self.cache:
                del self.cache[url]
            if url in self.timestamps:
                del self.timestamps[url]

    def clear(self) -> None:
        """Clear cache entries.

        Args:
            url: Specific URL to clear from cache, or None to clear all
        """
        self.cache.clear()
        self.timestamps.clear()


# Simple in-memory cache for HTTP responses
url_cache = URLCache(max_size=100, timeout=10 * 60)

# Simple in-memory cache for CNP to patient code mappings
cnp_cache: Dict[str, str] = {}
cache_max_size = 1000  # Maximum number of entries to cache


class UserSessionManager:
    """Manager for user-specific HTTP sessions."""

    def __init__(self):
        """Initialize the user session manager."""
        self.user_sessions: Dict[str, aiohttp.ClientSession] = {}

    def get_user_session(self, username: str):
        """Get or create a user-specific session.

        Args:
            username: Username to get session for

        Returns:
            aiohttp.ClientSession for the user
        """
        if username not in self.user_sessions or self.user_sessions[username].closed:
            logger.debug(f"Creating new aiohttp ClientSession for user {username} with cookie support")
            # Create session with automatic cookie handling
            self.user_sessions[username] = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
        else:
            logger.debug(f"Reusing existing aiohttp ClientSession for user {username}")
        return self.user_sessions[username]

    async def close_all_sessions(self):
        """Close all user sessions."""
        logger.info("Closing all user sessions")
        for username, session in self.user_sessions.items():
            if session and not session.closed:
                logger.debug(f"Closing aiohttp ClientSession for user {username}")
                await session.close()


# Global user session manager instance
user_session_manager = UserSessionManager()


class HipocrateClient:
    """Client for interacting with the Hipocrate medical system."""

    def __init__(self, service_url: str, username: str = None, password: str = None):
        """Initialize the Hipocrate client.

        Args:
            service_url: Base URL of the Hipocrate service
        """
        self.service_url = service_url
        self.headers = HEADERS.copy()
        self.url_cache = url_cache
        self.username = username
        self.password = password
        # Get session using the client's session manager
        self.session = None

    def set_credentials(self, username: str, password: str):
        """Set the username and password for authentication.

        Args:
            username: Username for Hipocrate service
            password: Password for Hipocrate service
        """
        self.username = username
        self.password = password


    def get_user_session(self, username: str):
        """Get or create a user-specific session.

        Args:
            username: Username to get session for

        Returns:
            aiohttp.ClientSession for the user
        """
        return user_session_manager.get_user_session(username)

    async def get_authenticated_session(self, username: str, password: str):
        """Get an authenticated session for the user.

        Args:
            username: Username for authentication
            password: Password for authentication

        Returns:
            Tuple of (session, success) where success is boolean
        """
        session = self.get_user_session(username)
        login_success = await self.login_if_needed(session, username, password)
        return session, login_success

    async def close_all_sessions(self):
        """Close all user sessions."""
        await user_session_manager.close_all_sessions()


    def cache_get(self, url: str) -> Optional[str]:
        """Get cached response for URL if exists and not expired.

        Args:
            url: URL to lookup

        Returns:
            Cached response text or None if not found or expired
        """
        return self.url_cache.get(self.get_full_url(url))

    def cache_put(self, url: str, response_text: str) -> None:
        """Add response to cache.

        Args:
            url: URL key
            response_text: Response text to cache
        """
        self.url_cache.put(self.get_full_url(url), response_text)

    def cache_remove(self, url: str):
        """Remove cached response for URL.

        Args:
            url: URL to lookup
        """
        return self.url_cache.remove(url)

    def cache_clear(self) -> None:
        """Clear cache entries.

        Args:
            url: Specific URL to clear from cache, or None to clear all
        """
        self.url_cache.clear()


    def is_login_page(self, content: str) -> bool:
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

    async def login_if_needed(self, session, username: str, password: str) -> bool:
        """Attempt to login to the Hipocrate service if needed.

        Checks if we're currently on the login page, and if so, performs login
        using the provided credentials.

        Args:
            session: The aiohttp session to use
            username: Username for login
            password: Password for login

        Returns:
            True if login was successful or not needed, False otherwise
        """
        logger.info("Attempting login if needed")

        if not username or not password:
            logger.warning("Username or password not set, skipping login")
            return False

        try:
            # First, check if we're already logged in by accessing main.asp
            main_url = f"{self.service_url}/main.asp"
            logger.debug(f"Checking if already logged in by accessing: {main_url}")
            async with session.get(main_url, headers=self.headers) as main_response:
                # Handle encoding properly - the service may not be using UTF-8
                try:
                    main_text = await self.handle_response_encoding(main_response)
                except UnicodeDecodeError:
                    # If UTF-8 fails, try to get raw bytes and decode with latin-1 or windows-1252
                    raw_data = await main_response.read()
                    try:
                        main_text = raw_data.decode('windows-1252')
                    except UnicodeDecodeError:
                        main_text = raw_data.decode('latin-1')
                logger.debug(f"Main page response status: {main_response.status}")

                # If we're not on the login page, we're already logged in
                if not self.is_login_page(main_text):
                    logger.info("Already logged in, skipping login")
                    return True

            # If we're on the login page, proceed with login
            logger.info("Not logged in, proceeding with login")

            # First, access the default.asp page to get initial cookies
            default_url = f"{self.service_url}/default.asp"
            logger.debug(f"Accessing default page to get cookies: {default_url}")
            async with session.get(default_url, headers=self.headers) as default_response:
                logger.debug(f"Default page response status: {default_response.status}")

            # Prepare login data to match browser submission
            login_data = {
                "id_recuperare_pwd_2": "",
                "strUser": username,
                "strPwd": password,
                "cboLang": "ro"
            }

            # Add referer header for the login request
            login_headers = self.headers.copy()
            login_headers["Referer"] = default_url

            # Use the correct login endpoint
            login_url = f"{self.service_url}/security/logon.asp"
            logger.debug(f"Submitting login form to {login_url}")
            # Submit login form
            async with session.post(
                login_url,
                data=login_data,
                headers=login_headers
            ) as login_response:
                response_text = await self.handle_response_encoding(login_response)
                logger.debug(f"Login response status: {login_response.status}")

                # Log cookie information
                if session.cookie_jar:
                    cookies = session.cookie_jar.filter_cookies(URL(self.service_url))
                    logger.debug(f"Session cookies after login: {len(cookies)} cookies")

            # Check if login was successful (redirect to main.asp or not on login page)
            if login_response.status == 302 and "main.asp" in login_response.headers.get("Location", ""):
                logger.info("Login successful: redirected to main.asp")
                return True
            elif not self.is_login_page(response_text):
                logger.info("Login successful: not on login page")
                return True
            else:
                logger.warning("Login failed: still on login page")
            return False
        except Exception as e:
            logger.error(f"Login failed with exception: {e}")
            return False

    async def handle_response_encoding(self, response):
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

    def get_full_url(self, url: str) -> str:
        """Construct full URL from service URL and relative path.

        Args:
            url: Relative path
        Returns:
            Full URL string
        """
        # Construct the full URL if a relative path is provided
        if url.startswith("http"):
            full_url = url
        elif url.startswith("/"):
            full_url = f'{self.service_url}{url}'
        else:
            full_url = f'{self.service_url}/{url}'
        return full_url

    async def post_form(self, url, data=None):
        """Submit a form to the Hipocrate service, following redirects.

        This method handles the common pattern of making authenticated POST requests.

        Args:
            url: The URL to submit the form to
            data: Form data to submit

        Returns:
            Tuple of (response_text, success, error_response) where success is boolean
        """
        # Construct the full URL if a relative path is provided
        current_url = self.get_full_url(url)

        # Get the session for the current user
        if not self.session:
            self.session = self.get_user_session(self.username)

        # Make the authenticated request
        start_time = datetime.now()
        response_text, success, error_response = await self.make_authenticated_request(
            current_url, "POST", data, self.username, self.password
        )
        duration = (datetime.now() - start_time).total_seconds()

        # Check for errors in the response
        if not success:
            return None, False, error_response
        logger.info(f"Response received in {duration:.2f} seconds")

        # Return the final response
        return response_text, True, None

    async def get_page(self, url, max_redirects=5):
        """Abstract method to retrieve a page from the Hipocrate service, following redirects.

        This method handles the common pattern of making authenticated requests with
        redirect following, which can be reused by derived classes.

        Args:
            url: The URL to request
            max_redirects: Maximum number of redirects to follow (default: 5)

        Returns:
            Tuple of (response_text, success, error_response) where success is boolean
        """
        # Construct the full URL if a relative path is provided
        current_url = self.get_full_url(url)

        # Get the session for the current user
        if not self.session:
            self.session = self.get_user_session(self.username)

        # Follow up to max_redirects redirects to get the final page data
        redirect_count = 0
        while redirect_count < max_redirects:
            # Make the authenticated request
            start_time = datetime.now()
            response_text, success, error_response = await self.make_authenticated_request(
                current_url, "GET", None, self.username, self.password
            )
            duration = (datetime.now() - start_time).total_seconds()

            # Check for errors in the response
            if not success:
                return None, False, error_response
            logger.info(f"Page retrieved in {duration:.2f} seconds")

            # Check if this is the final response (not a redirect)
            # We need to make a direct request to check the status code
            async with self.session.get(current_url, headers=self.headers) as response:
                logger.debug(f"Page request response status: {response.status}")

                # If we get the final data (not a redirect), break the loop
                if response.status != 302:
                    logger.info(f"Page retrieval completed successfully after {redirect_count} redirects")
                    return response_text, True, None

                # Handle 302 redirect
                location = response.headers.get("Location")
                if not location:
                    return None, False, create_error_response("Redirect without location header", 500)

                # Construct the full URL for the redirect
                if location.startswith("/"):
                    # Relative path from root - need to extract scheme and host from current_url
                    parsed_url = URL(current_url)
                    base_url = f"{parsed_url.scheme}://{parsed_url.host}"
                    current_url = f"{base_url}{location}"
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
        return None, False, create_error_response(f"Exceeded maximum redirects ({max_redirects})", 500)

    async def make_authenticated_request(self, url, method="GET", data=None, username=None, password=None):
        """Make an authenticated request to the Hipocrate service with automatic login handling.

        Args:
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
                async with self.session.get(url, headers=self.headers) as response:
                    response_text = await self.handle_response_encoding(response)
                    logger.debug(f"GET response status: {response.status}")
            else:  # POST
                logger.debug(f"Making POST request to: {url}")
                # For POST requests, we need to be careful about Content-Type headers
                # Create a copy of headers without Content-Type to avoid conflicts
                post_headers = self.headers.copy()
                if use_retry_headers or method == "POST":
                    post_headers.pop("Content-Type", None)
                # When sending form data, let aiohttp set the Content-Type automatically
                if data:
                    async with self.session.post(url, data=data, headers=post_headers) as response:
                        response_text = await self.handle_response_encoding(response)
                        logger.debug(f"POST response status: {response.status}")
                else:
                    async with self.session.post(url, headers=post_headers) as response:
                        response_text = await self.handle_response_encoding(response)
                        logger.debug(f"POST response status: {response.status}")
            return html.unescape(response_text)

        # Check if we have a cached response for GET requests
        if method == "GET":
            cached_response = self.cache_get(url)
            if cached_response is not None:
                return cached_response, True, None

        try:
            # Log current cookies before request
            if self.session.cookie_jar:
                cookies = self.session.cookie_jar.filter_cookies(URL(self.service_url))
                logger.debug(f"Using {len(cookies)} cookies for request to {url}")

            # Make the initial request
            response_text = await _make_request()

            # Check if we got redirected to login page (session expired)
            if self.is_login_page(response_text):
                logger.warning(f"Session expired during request to {url}, attempting re-login")
                login_success = await self.login_if_needed(self.session, username, password)
                if login_success:
                    # Retry the request with special headers for POST
                    response_text = await _make_request(use_retry_headers=True)
                    # Check again if still on login page
                    if self.is_login_page(response_text):
                        return None, False, create_error_response("Authentication failed after retry", 401)
                else:
                    return None, False, create_error_response("Re-authentication failed", 401)

            # Cache the response for GET requests
            if method == "GET":
                self.cache_put(url, response_text)

            # If we reach here, we have a valid response
            return response_text, True, None
        except Exception as e:
            return None, False, create_error_response(str(e), 500, {"URL": url})


# Extractors
# ###########################################################################

def extract_text_after_label(soup: BeautifulSoup, label_regex: str, element_tag: str = None, stop_at: str = None) -> str:
    """Extract field data from an element containing a label.

    Args:
        soup: BeautifulSoup object of the parsed HTML content
        label_regex: Regular expression pattern to match label text
        element_tag: HTML tag name to search for. If None, uses the own element of the label.
        stop_at: Optional string pattern to stop extraction at

    Returns:
        Extracted field content or empty string if not found
    """
    try:
        # Look for the element containing this label
        for label_element in soup.find_all(string=re.compile(label_regex, re.IGNORECASE)):
            # Check if this is a comment
            if isinstance(label_element, Comment):
                continue
            # Determine the container element to extract text from
            if element_tag is None:
                container_element = label_element.parent
            else:
                container_element = label_element.find_parent(element_tag)
            # If no container found, return empty
            if not container_element:
                return ""
            # Extract text content from the container and clean it
            # Remove the label part and get the rest
            container_text = container_element.get_text(separator=' ', strip=True)
            # Find the label in the text and extract everything after it
            match = re.search(label_regex, container_text, re.IGNORECASE)
            if match:
                # Get the position after the matched label
                label_end = match.end()
                # Extract the content after the label
                content = container_text[label_end:].strip()
                # If stop_at pattern is provided, truncate content at that point
                if stop_at:
                    stop_match = re.search(stop_at, content, re.IGNORECASE)
                    if stop_match:
                        content = content[:stop_match.start()].strip()
                # Return the cleaned content
                logger.debug(f"Extracted content for label '{label_regex}': {content}")
                return content
        # If label not found, return empty
        return ""
    except Exception as e:
        logger.error(f"Error extracting field with label '{label_regex}': {e}")
        return ""

def extract_id_from_link(link_element, id_pattern: str = r'id=([^&"]+)') -> Optional[str]:
    """Extract ID from a link element's href attribute.

    Args:
        link_element: BeautifulSoup element with href attribute
        id_pattern: Regex pattern to extract ID from href (default: r'id=([^&"]+)')

    Returns:
        Extracted ID string or None if not found
    """
    # Ensure link_element is valid
    if link_element:
        href = link_element.get('href', '')
        id_match = re.search(id_pattern, href)
        if id_match:
            return id_match.group(1)
    return None

def extract_ids_from_links(soup: BeautifulSoup, id_pattern: str = r'id=([^&"]+)') -> List[str]:
    """Extract IDs from multiple link elements' href attributes.

    Args:
        soup: BeautifulSoup object of the parsed HTML content
        id_pattern: Regex pattern to extract ID from href (default: r'id=([^&"]+)')

    Returns:
        List of extracted ID strings
    """
    ids_list = []
    for item in soup.find_all('a', href=re.compile(id_pattern)):
        href = item.get('href', '')
        id_match = re.search(id_pattern, href)
        if id_match:
            ids_list.append(id_match.group(1))
    return ids_list

def extract_value_from_input(soup: 'BeautifulSoup', id: str = None, name: str = None) -> str:
    if id:
        input_element = soup.find('input', id=id)
    elif name:
        input_element = soup.find('input', name=name)
    else:
        return ""
    if input_element:
        return input_element.get('value', '').strip()

def extract_textarea_after_label(soup: 'BeautifulSoup', label_regex: str) -> str:
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

def extract_tabular_data(soup: BeautifulSoup, identifier: str, identifier_type: str = "text") -> List[List[str]]:
    """Extract tabular data from an HTML table identified by text, id, or class.

    Args:
        soup: BeautifulSoup object of the parsed HTML content
        identifier: The text, id, or class to identify the table
        identifier_type: Type of identifier - "text", "id", or "class" (default: "text")

    Returns:
        List of rows, each row being a list of cell contents as plain text
    """
    try:
        # Find the table based on the identifier type
        table = None
        if identifier_type == "text":
            # Look for a table that contains the specified text
            text_elements = soup.find_all(string=re.compile(re.escape(identifier), re.IGNORECASE))
            for element in text_elements:
                # Check if the text is in a table header or cell
                parent = element.find_parent(['th', 'td', 'table'])
                if parent and parent.name == 'table':
                    table = parent
                    break
                elif parent:
                    # Find the containing table
                    table = parent.find_parent('table')
                    if table:
                        break
        elif identifier_type == "id":
            table = soup.find('table', id=identifier)
        elif identifier_type == "class":
            table = soup.find('table', class_=identifier)
        
        # If no table found, return empty list
        if not table:
            logger.debug(f"No table found with {identifier_type}: {identifier}")
            return []
        
        # Extract rows and cells
        rows = []
        for row in table.find_all('tr'):
            cells = []
            for cell in row.find_all(['td', 'th']):
                cell_text = cell.get_text(separator=' ', strip=True)
                cells.append(cell_text)
            # Only add non-empty rows
            if cells:
                rows.append(cells)
        
        logger.debug(f"Extracted {len(rows)} rows from table")
        return rows
        
    except Exception as e:
        logger.error(f"Error extracting tabular data: {e}")
        return []

# Authentication helpers
# ###########################################################################

def get_basic_auth(request):
    """Extract basic auth credentials from request.

    Args:
        request: The incoming HTTP request

    Returns:
        Tuple of (username, password) or None if not found
    """
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Basic '):
        return None

    try:
        encoded_credentials = auth_header.split(' ', 1)[1]
        decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
        username, password = decoded_credentials.split(':', 1)
        return (username, password)
    except Exception:
        return None

def require_auth(handler):
    """Decorator to require basic authentication for endpoints."""
    async def wrapper(request):
        # Get credentials from basic auth
        auth = get_basic_auth(request)
        if not auth:
            return web.Response(status=401, headers={'WWW-Authenticate': 'Basic realm="HippoBridge"'})
        # Extract username and password
        username, password = auth
        # Add credentials to request for use in handler
        request.auth_credentials = (username, password)
        # Call the original handler
        return await handler(request)
    # End of wrapper function
    return wrapper




@require_auth
async def get_patient(request):
    """Retrieve patient information by ID.

    Gets patient information from the Hipocrate service and extracts
    associated admission and discharge IDs.

    Args:
        request: The incoming HTTP request with 'id' query parameter for patient ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with patient data or error information
    """
    # Get patient ID from request path
    id = request.match_info.get('id')
    if not id:
        return create_error_response("Patient ID is required")
    logger.info(f"Retrieving patient with ID: {id}")

    # Get credentials from request (added by decorator)
    username, password = request.auth_credentials

    # Create a new HipocrateClient instance with credentials
    client = HipocrateClient(SERVICE_URL, username, password)

    try:
        # Make request to the patient endpoint
        request_url = f"/Pacient/edit.asp?id={id}"

        # Retrieve the page
        response_text, success, error_response = await client.get_page(request_url)

        # Check for errors in the response
        if not success:
            return error_response

        # Get patient details
        patient_data = parse_patient_data(response_text)
        if patient_data and patient_data.get("patient_id") and not patient_data.get("error"):
            fhir_patient = create_fhir_patient(patient_data, request)
            return web.json_response(fhir_patient)
        else:
            # Remove the cached response if patient not found
            client.cache_remove(request_url)
            # Return specific error if patient not found
            if patient_data and 'error' in patient_data:
                return create_error_response(patient_data['error'], 404)
            # Return an error if we couldn't read patient data
            return create_error_response("Unable to read patient data", 500)

    except Exception as e:
        return create_error_response("Patient retrieval failed", 500, {"exception": str(e)})

@require_auth
async def search_patient(request):
    """Search for patients by name or other criteria.

    Performs a patient search on the Hipocrate service using the provided search term.
    Can return either a single patient result or multiple patient results.
    If the search term ends with *, it's treated as a partial CNP search.

    Args:
        request: The incoming HTTP request with 'q' query parameter for search term
                 and basic auth credentials for authentication

    Returns:
        JSON response with search results or error information
    """
    # Get search parameter from query string
    search_term = request.query.get('q', '')
    if not search_term:
        return create_error_response("Search term is required")
    logger.info(f"Searching for patients with term: {search_term}")

    # Get credentials from request (added by decorator)
    username, password = request.auth_credentials

    # Create a new HipocrateClient instance with credentials
    client = HipocrateClient(SERVICE_URL, username, password)

    try:
        # Determine search type based on input
        search_type = "name"  # default

        # Check if search term is numeric
        if search_term.isdigit():
            # If it's 13 digits, validate as CNP
            if len(search_term) == 13:
                if validate_cnp(search_term):
                    search_type = "cnp"
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
                    logger.info(f"Performing partial CNP search for: {search_term}")
                else:
                    # Not a valid partial CNP, treat as name search
                    search_type = "name"
                    logger.info(f"Searching for patients by name: {search_term}")
            else:
                # Not numeric, treat as name search
                search_type = "name"
                logger.info(f"Searching for patients by name: {search_term}")

        # Prepare full search data as captured in the POST request
        search_data = {
            "hdnSearchType": "1",
            "pageNo": "1",
            "strDescription": search_term if search_type in ["name", "code", "cnp", "partial_cnp"] else "",
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
        request_url = f"/files/search.asp?what=PA"

        # Post the request
        response_text, success, error_response = await client.post_form(request_url, search_data)

        # Check for errors in the response
        if not success:
            return error_response


        ## Try to parse as single patient page first
        patient_data = parse_patient_data(response_text)
        if patient_data and patient_data.get("patient_id") and not patient_data.get("error"):
            fhir_patient = create_fhir_patient(patient_data, request)
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
            for patient_id, patient_name in multiple_patients_data.items():
                # Split patient name into family and given names
                name_parts = patient_name.split()
                family_name = name_parts[0] if len(name_parts) > 0 else ""
                given_names = name_parts[1:] if len(name_parts) > 1 else []
                # Create FHIR Patient resource
                fhir_patient = {
                    "resourceType": "Patient",
                    "id": patient_id,
                    "name": [
                        {
                            "use": "official",
                            "family": family_name,
                            "given": given_names
                        }
                    ]
                }
                # Add entry to bundle
                bundle["entry"].append({
                    "resource": fhir_patient
                })
            return web.json_response(bundle)

        # Check if we're on a "no results" page
        # TODO This is not working
        if "nu a fost gasit" in response_text.lower() or "no results" in response_text.lower():
            # Return empty FHIR Bundle
            bundle = {
                "resourceType": "Bundle",
                "type": "searchset",
                "total": 0,
                "entry": []
            }
            return web.json_response(bundle)

        # Log a snippet of the response for debugging
        return create_error_response(
            "Unable to parse patient search results",
            500,
            {"text": response_text[:300] + "..."}
        )

    except Exception as e:
        return create_error_response("Patient search failed", 500, {"exception": str(e)})

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
    # Initialize empty patient data dictionary
    patient_data = {}

    # Inner function to extract data from input elements
    def get_data_from(data_key: str, input_id: str) -> None:
        input_element = soup.find('input', id=input_id)
        if input_element:
            patient_data[data_key] = input_element.get('value', '').strip()

    try:
        # Parse HTML content with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

        # Check if this is a single patient page by looking for 'Date pasaportale' in title
        if not is_expected_page(soup, 'Date pasaportale'):
            # Log snnippet of response for debugging
            return create_error_response("Backend returned an unexpected page", 500, {"text": html_content[:200] + "..."})

        # Check if there is patient data on page by getting the name from the div with id "div_navbar"
        navbar_div = soup.find('div', id='div_navbar')
        if not navbar_div:
            return create_error_response("Invalid patient id", 404)
        patient_name_from_navbar = navbar_div.get_text().strip()
        if not patient_name_from_navbar:
            return create_error_response("Patient name from navbar is empty, invalid patient id", 404)

        # Patient name
        patient_data["patient_name"] = patient_name_from_navbar

        # Extract patient name from input elements
        get_data_from("family_name", "strNume")
        get_data_from("given_name", "strPrenume")
        if patient_data.get("family_name") and patient_data.get("given_name"):
            patient_data["patient_name"] = f"{patient_data['family_name']} {patient_data['given_name']}".strip()

        # Extract patient CNP from input element with id "strCNP"
        get_data_from("patient_cnp", "strCNP")

        # Extract patient id from hidden input with id "hdnCodeID"
        get_data_from("patient_id", "hdnCodeID")

        # Extract CID
        get_data_from("cid", "strCID")

        # Extract phone
        get_data_from("phone", "strTelefon")

        # Extract email
        get_data_from("email", "strEmail")

        # Extract weight
        get_data_from("weight", "strGreutate")

        # Extract height
        get_data_from("height", "strInaltime")

        # Extract MCP
        get_data_from("mcp", "strmcp")

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
        encounter_ids = extract_ids_from_links(soup, r'../files/presentation\.asp\?id=(\d+)')
        if encounter_ids:
            patient_data["encounters"] = encounter_ids

        # Extract admissions / checkins
        admission_ids = extract_ids_from_links(soup, r'../files/checkin\.asp\?id=(\d+)')
        if admission_ids:
            patient_data["admissions"] = admission_ids

        # Extract discharges / checkouts
        discharge_ids = extract_ids_from_links(soup, r'../files/checkout\.asp\?id=(\d+)')
        if discharge_ids:
            patient_data["discharges"] = discharge_ids

        # Return the extracted patient data
        return patient_data
    except Exception as e:
        logger.error(f"Error parsing patient data: {e}")
        return {}

def parse_multiple_patients_data(html_content: str) -> Dict[str, Any]:
    """Parse HTML content for multiple patient search results and extract patient data.

    Extracts patient names, CNP, and ids from search results page with multiple patients.

    Args:
        html_content: HTML content of the search results page

    Returns:
        List of dictionaries containing patient data (name, ID only)
    """
    # Initialize empty list for patients
    patients = {}

    try:
        # Parse HTML content with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

        # Check if this is a search results page by looking for 'Fisier' in title
        if not is_expected_page(soup, 'Fisier'):
            # Log snippet of response for debugging
            #logger.debug(f"Response text snippet: {html_content[:200]}...")
            # Return empty list if not expected page
            return patients

        # Find all links with the pattern javascript:Edit('patient_id')
        pattern = r"javascript:Edit\('([^']+)'\);"
        for link in soup.find_all('a', href=re.compile(pattern)):
            # Extract patient id from href
            patient_id = extract_id_from_link(link, pattern)
            if not patient_id:
                continue

            # Extract patient name from the link text
            patient_name = link.get_text().strip().upper()
            if patient_name == patient_id:
                # If name is same as id, skip this entry (the data is duplicated in Hipocrate)
                continue

            # Add patient data to list
            patients[patient_id] = patient_name
        # Return the list of patients
        return patients

    except Exception as e:
        logger.error(f"Error parsing multiple patients data: {e}")
        return patients

def create_fhir_patient(patient_data: Dict[str, Any], request) -> Dict[str, Any]:
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

    # Create FHIR Patient resource using the FHIR class
    fhir_patient = FHIRPatient(
        id=patient_data.get("patient_id", ""),
        active=True,
        gender=gender,
        birthDate=birth_date
    )

    # Add name
    name = {
        "use": "official",
        "family": family_name,
        "given": given_names
    }
    fhir_patient["name"] = [name]

    # Add telecom information if available
    telecom = []
    if patient_data.get("phone", None):
        telecom.append({
            "system": "phone",
            "value": patient_data["phone"]
        })

    if patient_data.get("email", None):
        telecom.append({
            "system": "email",
            "value": patient_data["email"]
        })

    if telecom:
        fhir_patient["telecom"] = telecom

    # Add address information if available
    address = []
    if patient_data.get("address", None):
        address.append({
            "text": patient_data["address"]
        })

    if address:
        fhir_patient["address"] = address

    # Add extensions for additional patient data
    extensions = []

    # Add weight if available
    if patient_data.get("weight", None):
        extensions.append({
            "url": "http://hl7.org/fhir/us/vitals/StructureDefinition/body-weight",
            "valueString": patient_data["weight"]
        })

    # Add height if available
    if patient_data.get("height", None):
        extensions.append({
            "url": "http://hl7.org/fhir/us/vitals/StructureDefinition/height",
            "valueString": patient_data["height"]
        })

    # Add extensions for encounter/admission/discharge IDs
    if "encounters" in patient_data:
        extensions.append({
            "url": f"{request.scheme}://{request.host}/fhir/StructureDefinition/encounter-ids",
            "valueString": ",".join(patient_data["encounters"])
        })
    if "admissions" in patient_data:
        extensions.append({
            "url": f"{request.scheme}://{request.host}/fhir/StructureDefinition/admission-ids",
            "valueString": ",".join(patient_data["admissions"])
        })
    if "discharges" in patient_data:
        extensions.append({
            "url": f"{request.scheme}://{request.host}/fhir/StructureDefinition/discharge-ids",
            "valueString": ",".join(patient_data["discharges"])
        })

    if extensions:
        fhir_patient["extension"] = extensions

    # Add identifiers
    identifiers = []

    # Add CNP as identifier if available
    if patient_data.get("patient_cnp", None):
        identifiers.append({
            "use": "official",
            "system": f"{request.scheme}://{request.host}/fhir/NamingSystem/patient-cnp",
            "value": patient_data["patient_cnp"]
        })

    # Add CID if available
    if patient_data.get("cid", None):
        identifiers.append({
            "system": f"{request.scheme}://{request.host}/fhir/NamingSystem/patient-cid",
            "value": patient_data["cid"]
        })

    # Add MCP if available
    if patient_data.get("mcp", None):
        identifiers.append({
            "system": f"{request.scheme}://{request.host}/fhir/NamingSystem/patient-mcp",
            "value": patient_data["mcp"]
        })

    if identifiers:
        fhir_patient["identifier"] = identifiers

    # Return the FHIR Patient resource as dict
    return fhir_patient.to_dict()


@require_auth
async def get_diagnostic_report(request):
    """Retrieve a diagnostic report by ID, following redirect chains.

    Gets a diagnostic report from the Hipocrate service, following any redirects to
    retrieve the final report data, then parses it into structured format.

    Args:
        request: The incoming HTTP request with 'id' path parameter for report ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with diagnostic report data or error information
    """
    # Extract report ID from path
    id = request.match_info.get('id')
    if not id:
        return create_error_response("Report ID is required")
    logger.info(f"Retrieving report with ID: {id}")

    # Get credentials from request (added by decorator)
    username, password = request.auth_credentials

    # Create a new HipocrateClient instance with credentials
    client = HipocrateClient(SERVICE_URL, username, password)

    try:
        # The report endpoint
        request_url = f"/analyse/Reports/analyseFile.asp?id={id}"

        # Retrieve the page
        response_text, success, error_response = await client.get_page(request_url)

        # Check for errors in the response
        if not success:
            return error_response

        # Return DiagnosticReport
        report_data = parse_report_data(response_text)
        report_data['report_id'] = id
        fhir_response = create_fhir_diagnostic_report(report_data, request)
        return web.json_response(fhir_response)

    except Exception as e:
        return create_error_response("Report retrieval failed", 500, {"exception": str(e)})

@require_auth
async def get_imaging_study(request):
    """Retrieve an imaging study by ID, following redirect chains.

    Gets an imaging study from the Hipocrate service, following any redirects to
    retrieve the final report data, then parses it into structured format.

    Args:
        request: The incoming HTTP request with 'id' path parameter for study ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with imaging study data or error information
    """
    # Extract study ID from path
    id = request.match_info.get('id')
    if not id:
        return create_error_response("Study ID is required")
    logger.info(f"Retrieving study with ID: {id}")

    # Get credentials from request (added by decorator)
    username, password = request.auth_credentials

    # Create a new HipocrateClient instance with credentials
    client = HipocrateClient(SERVICE_URL, username, password)

    try:
        # The study endpoint
        request_url = f"/analyse/Reports/analyseFile.asp?id={id}"

        # Retrieve the page
        response_text, success, error_response = await client.get_page(request_url)

        # Check for errors in the response
        if not success:
            return error_response

        # Return ImagingStudy
        report_data = parse_report_data(response_text)
        report_data['report_id'] = id
        fhir_response = create_fhir_imaging_study(report_data, request)
        return web.json_response(fhir_response)

    except Exception as e:
        return create_error_response("Imaging study retrieval failed", 500, {"exception": str(e)})

def parse_report_data(html_content: str) -> Dict[str, Any]:
    """Parse HTML report content and extract structured data.

    Extracts patient information, examination details, and report results
    from HTML report content.

    Args:
        html_content: HTML content of the report

    Returns:
        Dictionary containing parsed report data
    """
    # Initialize report data dictionary
    report_data = {
        "patient_name": "",
        "age": "",
        "gender": "",
        "patient_cnp": "",
        "patient_id": "",
        "datetime": "",
        "date": "",
        "time": "",
        "examination": "",
        "reports": [],
        "performer": ""
    }

    try:
        # Parse HTML content with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

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

        # Extract date and time
        datetime_match = re.search(r'(?:Data si ora recoltarii:|Data investigatiei:)\s*([^\n\r<>&]+)', text_content, re.IGNORECASE)
        dt = None  # Initialize dt variable
        if datetime_match:
            datetime_str = re.sub(r'\s+', ' ', datetime_match.group(1).strip())
            # Try to parse date and time
            try:
                # Handle common date formats
                if re.match(r'\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}', datetime_str):
                    dt = datetime.strptime(datetime_str, '%d/%m/%Y %H:%M:%S')
                elif re.match(r'\d{2}/\d{2}/\d{4}', datetime_str):
                    dt = datetime.strptime(datetime_str, '%d/%m/%Y')
            except ValueError:
                # If parsing fails, leave date/time fields empty
                pass
        report_data["datetime"] = dt

        # Extract performer (Efectuata de catre:)
        performer_match = re.search(r'(?:Efectuata de catre:)\s*([^\n\r<>&]+)', text_content, re.IGNORECASE)
        if performer_match:
            report_data["performer"] = re.sub(r'\s+', ' ', performer_match.group(1).strip())

        # Extract fields using the helper function
        report_data["examination"] = extract_text_after_label(soup, r'EXAMINARE EFECTUATA:', 'td')

        # Extract modality from examination text
        examination_text = report_data["examination"].lower() if report_data["examination"] else ""
        modality_mapping = {
            'radiografia': 'CR',    # Computed Radiography
            'ultrasonografia': 'US',    # Ultrasound
            'tomografia': 'CT',    # Computed Tomography
            'rezonanta': 'MR',    # Magnetic Resonance
            'angiografia': 'XA',    # X-Ray Angiography
            'cisto': 'RF'     # Radio Fluoroscopy
        }

        # Check if any modality code is in the examination text
        for key, modality in modality_mapping.items():
            if key in examination_text:
                report_data["modality"] = modality
                break

        report_data["referral_reason"] = extract_text_after_label(soup, r'DIAGNOSTIC DE TRIMITERE:', 'td')
        report_data["presumptive_diagnosis"] = extract_text_after_label(soup, r'DG\.PREZUMTIV:', 'td')
        report_data["special_indications"] = extract_text_after_label(soup, r'INDICATII SPECIALE:', 'td')
        report_data["referring_physician"] = extract_text_after_label(soup, r'TRIMIS DE:\s*MEDIC', 'td', stop_at=r'SECTIA')

        # Parse referral code and reason if we have referral data
        if report_data["referral_reason"]:
            # Split into code and text - first part numeric is the code, rest is the reason
            parts = report_data["referral_reason"].split(' ', 1)
            if parts:
                # Check if first part is numeric (the code)
                if parts[0].isdigit():
                    report_data["referral_code"] = parts[0]
                    report_data["referral_reason"] = parts[1].strip() if len(parts) > 1 else ""

        # Extract multiple reports: find all elements with text starting with "REZULTAT:"
        for result_element in soup.find_all(string=re.compile(r'^REZULTAT:', re.IGNORECASE)):
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

        # Extract interpreter (MEDIC, or Medic validator:)
        # Handle both plain text and HTML formatted interpreter names
        interpreter_patterns = [
            r'(?:MEDIC,|Medic validator:)\s*([^\n\r<>&]+)',
            r'(?:MEDIC,|Medic validator:)\s*<b[^>]*>([^<]+)</b>',
            r'(?:MEDIC,|Medic validator:)[^>]*>\s*([^\n\r<>&]+)'
        ]
        interpreter_name = ""
        for pattern in interpreter_patterns:
            interpreter_match = re.search(pattern, html_content, re.IGNORECASE)
            if interpreter_match:
                interpreter_name = interpreter_match.group(1).strip()
                # Clean up HTML entities and extra whitespace
                interpreter_name = html.unescape(interpreter_name)
                interpreter_name = re.sub(r'\s+', ' ', interpreter_name)
                break
        if interpreter_name:
            report_data["interpreter"] = interpreter_name
        # Return the parsed report data
        return report_data

    except Exception as e:
        logger.error(f"Error parsing report data: {e}")
        return {}

def parse_report(html_content: str) -> Dict[str, Any]:
    """Parse HTML report content and extract structured data from report.html format.

    Extracts patient information, examination details, and report results
    from HTML report content in the specific format shown in report.html.

    Args:
        html_content: HTML content of the report

    Returns:
        Dictionary containing parsed report data
    """
    # Initialize report data dictionary
    report_data = {
        "patient_name": "",
        "patient_age": "",
        "patient_gender": "",
        "patient_cnp": "",
        "patient_id": "",
        "physician": "",

        "examination": "",
        "reports": [],
        "performer": "",
        "validator": "",
        "validation_datetime": "",
        "barcode": "",
        "admission_id": "",
        "diagnosis": "",
        "clinical_comments": "",
        "lab_comments": "",
        "procedures": [],
        "request_datetime": "",
        "is_urgent": "~URGENTA~" in html_content
    }

    # Inner function to extract data from input elements
    def store_data(data_key: str, value: str) -> None:
        if value:
            if isinstance(value, str):
                report_data[data_key] = value.strip()
            else:
                report_data[data_key] = value

    try:
        # Parse HTML content with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

        # Extract tabular data from table with id="D1" for debugging
        #debug_table_data = extract_tabular_data(soup, "D1", "id")
        #print(f"DEBUG: Table D1 data: {debug_table_data}")

        # Extract patient name from the table with patient data
        store_data("patient_name", extract_text_after_label(soup, r'Nume:', 'tr', stop_at=r'\['))

        # Extract age
        store_data("patient_age", extract_text_after_label(soup, r'Varsta:', 'tr'))

        # Extract gender
        store_data("patient_gender", extract_text_after_label(soup, r'Sex:', 'td'))

        # Extract patient CNP from the table with patient data
        patient_cnp = extract_value_from_input(soup, id="strCNP")
        store_data("patient_cnp", patient_cnp)
        parsed_cnp = parse_cnp(patient_cnp)
        store_data("patient_gender", parsed_cnp.get("gender", ""))
        store_data("birth_date", parsed_cnp.get("birth_date", ""))
        store_data("patient_age", parsed_cnp.get("age", ""))

        # Extract patient code from the table with patient data
        patient_ids = extract_ids_from_links(soup, r'/pacient/edit\.asp\?id=(\d+)')
        store_data("patient_id", patient_ids[0])

        # Extract physician
        store_data("physician", extract_text_after_label(soup, r'Medic:', 'tr'))

        # Extract diagnostis
        store_data("diagnosis", extract_text_after_label(soup, r'Diagnostic:', 'tr'))

        # Extract requester and request date and time
        req = extract_text_after_label(soup, r'Ceruta:', 'tr')
        request_physician, request_datetime = req.split('-')
        store_data("request_physician", request_physician)
        # Try to parse the datetime
        dt = parse_date_time(request_datetime)
        if dt:
            report_data["request_datetime"] = dt.isoformat()
        else:
            # If parsing fails, keep the original string
            report_data["request_datetime"] = request_datetime

        # Extract performer (validator) from the domain section
        validator = extract_text_after_label(soup, r'Validat de:', 'td', stop_at=r'Data')
        if validator:
            report_data["validator"] = validator

        # Extract validation datetime
        validation_datetime = extract_value_from_input(soup, id="dataefectuarii")
        if validation_datetime:
            # Try to parse the datetime
            dt = parse_date_time(validation_datetime)
            if dt:
                report_data["validation_datetime"] = dt.isoformat()
            else:
                # If parsing fails, keep the original string
                report_data["validation_datetime"] = validation_datetime
        
        # For each strAnalyseExec input, find the parent 'td' and extract examination name from first 'b' element
        for input_elem in soup.find_all('input', {'name': 'strAnalyseExec'}):
            parent_td = input_elem.find_parent('td')
            if parent_td:
                first_b = parent_td.find('b')
                print(first_b.get_text(strip=True))
                # Find the 'table' parent and then the 'center' sibling
                parent_table = parent_td.find_parent('table')
                container = parent_table.find_next_sibling('center')
                procedure_result = None
                if container:
                    # In 'center' there is another table.
                    # The rows containing 'rezultat' in first 'td' have the result in second 'td'
                    for row in container.find_all('tr'):
                        cells = row.find_all('td')
                        if len(cells) >= 2:
                            if cells[0].get_text(strip=True).lower() == "rezultat":
                                # Filter out text nodes that contain only whitespace
                                subelements = [child for child in cells[1] if hasattr(child, 'name') and child.name]
                                if len(subelements) == 1 and subelements[0].name == 'b':
                                    # If the only child is a <b> tag, use its content directly
                                    procedure_result = html_to_markdown(str(subelements[0]))
                                else:
                                    # Otherwise, process the entire div
                                    procedure_result = html_to_markdown(str(cells[1]))
                # Append the procedure if the data is valid
                if first_b and procedure_result:
                    procedure = {
                        "title" : first_b.get_text(strip=True),
                        "result": procedure_result,
                        "type": "",
                        "region": ""
                        }
                    report_data["procedures"].append(procedure)

        # Return the parsed report data
        return report_data

    except Exception as e:
        logger.error(f"Error parsing report data: {e}")
        return {}

def create_fhir_diagnostic_report(report_data: Dict[str, Any], request) -> Dict[str, Any]:
    # Create enhanced FHIR DiagnosticReport resource
    fhir_report = {
        "resourceType": "DiagnosticReport",
        "id": report_data["report_id"],
        "status": "final",
        "code": {
            "coding": [
                {
                    "system": f"{request.scheme}://{request.host}/fhir/CodeSystem/report-types",
                    "code": "imaging-report",
                    "display": "Imaging Report"
                }
            ],
            "text": report_data.get("examination", "Imaging Report")
        },
        "subject": {
            "reference": f"Patient/{report_data.get('patient_id', '')}"
        },
        "basedOn": {
            "reference": f"ServiceRequest/{report_data.get('report_id')}"
        },
        "imagingStudy": {
            "reference": f"ImagingStudy/{report_data['report_id']}"
        },

    }

    # Add effective date if available
    if report_data.get("datetime"):
        # Ensure datetime is in proper ISO format
        if isinstance(report_data["datetime"], datetime):
            fhir_report["effectiveDateTime"] = report_data["datetime"].isoformat()
        else:
            fhir_report["effectiveDateTime"] = report_data["datetime"]

    # Add performer if available
    if report_data.get("performer"):
        fhir_report["performer"] = [
            {
                "display": report_data["performer"]
            }
        ]

    # Add results interpreter if available
    if report_data.get("interpreter"):
        fhir_report["resultsInterpreter"] = [
            {
                "display": report_data["interpreter"]
            }
        ]

    # Add results if available
    if report_data.get("reports"):
        fhir_report["result"] = [
            {
                "reference": f"Observation/{report_data['report_id']}"
            }
        ]

        # Add full report text from the first report result
        fhir_report["presentedForm"] = []
        for report in report_data["reports"]:
            # Convert HTML to markdown - no need to encode as base64 since it's text
            markdown_content = html_to_markdown(report["result"])
            fhir_report["presentedForm"].append(
                {
                    "contentType": "text/markdown",
                    "data": markdown_content
                }
            )

        # Add the first report's result text to conclusion
        first_report_result = report_data["reports"][0]["result"] if report_data["reports"] else ""
        fhir_report["conclusion"] = html_to_markdown(first_report_result)

    # Add media references placeholder
    fhir_report["media"] = []

    # Add extensions for referer and reason code/text if available
    extensions = []

    # Add referer if available
    if report_data.get("referring_physician"):
        extensions.append({
            "url": f"{request.scheme}://{request.host}/fhir/StructureDefinition/diagnostic-report-referer",
            "valueString": report_data["referring_physician"]
        })

    # Add reason code and text if available
    if report_data.get("referral_code") or report_data.get("referral_reason"):
        reason_extension = {
            "url": f"{request.scheme}://{request.host}/fhir/StructureDefinition/diagnostic-report-reason",
            "extension": []
        }

        if report_data.get("referral_code"):
            reason_extension["extension"].append({
                "url": "code",
                "valueString": report_data["referral_code"]
            })

        if report_data.get("referral_reason"):
            reason_extension["extension"].append({
                "url": "text",
                "valueString": report_data["referral_reason"]
            })

        extensions.append(reason_extension)

    if extensions:
        fhir_report["extension"] = extensions

    # Return the FHIR Patient resource
    return fhir_report

def create_fhir_imaging_study(report_data: Dict[str, Any], request) -> Dict[str, Any]:
    """Convert report data to FHIR ImagingStudy resource format.

    Args:
        report_data: Report data from parse_report_data
        request: The HTTP request object to get the host

    Returns:
        FHIR ImagingStudy resource
    """
    # Create FHIR ImagingStudy resource
    fhir_imaging_study = {
        "resourceType": "ImagingStudy",
        "id": report_data["report_id"],
        "status": "available",
        "subject": {
            "reference": f"Patient/{report_data.get('patient_id', '')}"
        },
        "basedOn": {
            "reference": f"ServiceRequest/{report_data.get('report_id')}"
        },
        "started": report_data["datetime"].isoformat() if report_data.get("datetime") else datetime.now().isoformat(),
        "series": []
    }

    # Add modality if available
    if report_data.get("modality"):
        fhir_imaging_study["modality"] = {
            "system": "http://dicom.nema.org/resources/ontology/DCM",
            "code": report_data["modality"].upper(),
            "display": report_data["modality"].upper()
        }

    # Add patient information if available
    if report_data.get("patient_name"):
        fhir_imaging_study["identifier"] = [{
            "system": f"{request.scheme}://{request.host}/fhir/NamingSystem/patient-name",
            "value": report_data["patient_name"]
        }]

    if report_data.get("patient_cnp"):
        if "identifier" not in fhir_imaging_study:
            fhir_imaging_study["identifier"] = []
        fhir_imaging_study["identifier"].append({
            "system": f"{request.scheme}://{request.host}/fhir/NamingSystem/patient-cnp",
            "value": report_data["patient_cnp"]
        })

    # Add description from examination
    if report_data.get("examination"):
        fhir_imaging_study["description"] = report_data["examination"]

    # Add performer if available
    if report_data.get("performer"):
        fhir_imaging_study["performer"] = [
            {
                "actor": {
                    "display": report_data["performer"]
                }
            }
        ]

    # Add referrer if referring physician is available
    if report_data.get("referring_physician"):
        fhir_imaging_study["referrer"] = {
            "display": report_data["referring_physician"]
        }

    # Add series for each report
    if report_data.get("reports"):
        for i, report in enumerate(report_data["reports"]):
            series = {
                "uid": f"urn:oid:1.2.840.99999999.1.{report_data['report_id']}.{i+1}",
                "number": i+1,
                "modality": {
                    "system": "http://dicom.nema.org/resources/ontology/DCM",
                    "code": "OT",  # Other
                    "display": "Other"
                },
                "description": report.get("investigation", "Imaging Study"),
                "started": report_data["datetime"].isoformat() if report_data.get("datetime") else datetime.now().isoformat(),
                "instance": []
            }
            # Use the study modality for the series if available, otherwise default to OT
            series_modality = report_data.get("modality", "OT")
            series["modality"] = {
                "system": "http://dicom.nema.org/resources/ontology/DCM",
                "code": series_modality.upper(),
                "display": series_modality.upper()
            }
            # Add the instance
            fhir_imaging_study["series"].append(series)

    # Add reason for study if referral information is available
    if report_data.get("referral_reason") or report_data.get("referral_code"):
        reason_text = ""
        if report_data.get("referral_code"):
            reason_text += f"Code: {report_data['referral_code']}"
        if report_data.get("referral_reason"):
            if reason_text:
                reason_text += " - "
            reason_text += report_data["referral_reason"]

        fhir_imaging_study["reason"] = [
            {
                "text": reason_text
            }
        ]

    # Add note if presumptive diagnosis is available
    if report_data.get("presumptive_diagnosis"):
        fhir_imaging_study["note"] = [
            {
                "text": report_data["presumptive_diagnosis"]
            }
        ]

    # Add description if special _indications are available
    if report_data.get("special_indications"):
        fhir_imaging_study["description"] = report_data["presumptive_diagnosis"]

    return fhir_imaging_study

@require_auth
async def get_observation(request):
    """Retrieve a single observation by ID.

    Gets detailed information for a specific observation from the Hipocrate service.

    Args:
        request: The incoming HTTP request with 'id' path parameter for observation ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with observation data or error information
    """
    # Extract observation ID from path
    id = request.match_info.get('id')
    if not id:
        return create_error_response("Observation ID is required")
    logger.info(f"Retrieving observation with ID: {id}")

    # Get credentials from request (added by decorator)
    username, password = request.auth_credentials

    # Create a new HipocrateClient instance with credentials
    client = HipocrateClient(SERVICE_URL, username, password)

    try:
        # The observation endpoint
        #request_url = f"/analyse/Reports/analyseFile_4212-lab.asp?fullpacient=yes&id={id}&section=4212-lab"
        request_url = f"/analyse/labrequest/edit.asp?id={id}"


        # Retrieve the page
        response_text, success, error_response = await client.get_page(request_url)

        # Check for errors in the response
        if not success:
            return error_response

        # Return Observation
        report_data = parse_report(response_text)
        report_data['report_id'] = id
        #fhir_response = create_fhir_observation(report_data, request)
        #return web.json_response(fhir_response)
        return web.json_response(report_data)

    except Exception as e:
        return create_error_response("Observation retrieval failed", 500, {"exception": str(e)})

def create_fhir_observation(report_data: Dict[str, Any], request) -> Dict[str, Any]:
    """Convert report data to FHIR ImagingStudy resource format.

    Args:
        report_data: Report data from parse_report_data
        request: The HTTP request object to get the host

    Returns:
        FHIR ImagingStudy resource
    """
    # Create FHIR Observation resource
    fhir_observation = {
        "resourceType": "Observation",
        "id": report_data["report_id"],
        "status": "final",
        "code": {
            "coding": [
                {
                    "system": f"{request.scheme}://{request.host}/fhir/CodeSystem/analysis-types",
                    "code": "unknown",
                    "display": "Analysis"
                }
            ],
            "text": report_data.get("examination", "Analysis")
        },
        "subject": {
            "reference": f"Patient/{report_data.get('patient_id', '')}"
        },
        "basedOn": {
            "reference": f"ServiceRequest/{report_data.get('report_id')}"
        },
    }

    # Add effective datetime if available
    if report_data.get("datetime"):
        fhir_observation["effectiveDateTime"] = report_data["datetime"].isoformat()

    # Add performer if available
    if report_data.get("performer"):
        fhir_observation["performer"] = [
            {
                "display": report_data["performer"]
            }
        ]

    # Add value/comment if available
    if report_data.get("reports"):
        fhir_observation["note"] = []
        for report in report_data["reports"]:
            fhir_observation["note"].append(
                {
                    "contentType": "text/plain",
                    "data": report["result"]
                }
            )

    return fhir_observation

@require_auth
async def search_observation(request):
    """Retrieve list of observations for a patient by ID.

    Gets a list of observations for a specific patient from the Hipocrate service
    without fetching detailed data for each observation.

    Args:
        request: The incoming HTTP request with 'patient' query parameter for patient ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with observations data or error information
    """
    # Extract patient ID from query parameters
    patient_id = request.query.get('patient')
    if not patient_id:
        return create_error_response("Patient ID is required")
    logger.info(f"Retrieving analyses list for patient with ID: {patient_id}")

    # Get credentials from request (added by decorator)
    username, password = request.auth_credentials

    # Create a new HipocrateClient instance with credentials
    client = HipocrateClient(SERVICE_URL, username, password)

    # Get optional parameters
    exam_type = request.query.get('type')
    exam_region = request.query.get('region')
    exam_datetime = request.query.get('dt')
    full_data = request.query.get('full', 'no').lower() == 'yes'

    try:
        # The analyses endpoint
        request_url = f"/pacient/analyses.asp?type=PA&pacid={patient_id}"
        # Add full=yes parameter if requested
        if full_data:
            request_url += "&full=yes"

        # Retrieve the page
        response_text, success, error_response = await client.get_page(request_url)

        # Check for errors in the response
        if not success:
            return error_response

        # Parse the analyses data to extract report IDs, types, and patient name
        parsed_data = parse_analyses_data(response_text)

        # Filter analyses by type if specified
        analyses = parsed_data["analyses"]
        if exam_type:
            analyses = [a for a in analyses if a["type"] == exam_type]

        # Filter analyses by datetime if specified
        if exam_datetime:
            # Parse the datetime string to match against analysis datetimes
            try:
                target_dt = datetime.fromisoformat(exam_datetime.replace('Z', '+00:00'))
                # Start with a date range from one day earlier to one day after
                hours_range = 24
                max_attempts = 3

                for attempt in range(max_attempts):
                    start_dt = target_dt - timedelta(hours=hours_range)
                    end_dt = target_dt + timedelta(hours=hours_range)

                    filtered_analyses = []
                    for a in analyses:
                        if "datetime" in a and start_dt <= a["datetime"] <= end_dt:
                            filtered_analyses.append(a)

                    # If we found exactly one observation, return it
                    if len(filtered_analyses) == 1:
                        analyses = filtered_analyses
                        break
                    # If we found multiple observations, reduce the time range and try again
                    elif len(filtered_analyses) > 1 and attempt < max_attempts - 1:
                        hours_range = hours_range / 2
                        continue
                    # If no observations or on final attempt, return what we found
                    else:
                        analyses = filtered_analyses
                        break

            except ValueError:
                logger.warning(f"Invalid datetime format: {exam_datetime}")

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
                "status": "final",
                "code": {
                    "coding": [
                        {
                            "system": f"{request.scheme}://{request.host}/fhir/CodeSystem/analysis-types",
                            "code": analysis["type"],
                            "display": ANALYSIS_TYPES[analysis["type"]]["display"]
                        }
                    ],
                    "text": ANALYSIS_TYPES[analysis["type"]]["definition"]
                },
                "subject": {
                    "reference": f"Patient/{patient_id}"
                },
                "basedOn": {
                    "reference": f"ServiceRequest/{analysis.get('analysis_id')}"
                },
            }

            # Add effective datetime if available
            if analysis.get("datetime"):
                fhir_observation["effectiveDateTime"] = analysis["datetime"].isoformat()

            bundle["entry"].append({
                "resource": fhir_observation
            })

        return web.json_response(bundle)

    except Exception as e:
        return create_error_response("Analyses list retrieval failed", 500, {"exception": str(e)})

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

        # Find all links to analysis
        for link in soup.find_all('a', href=re.compile(r'../analyse/Reports/analyseFile\.asp\?id=\d+')):
            # Extract analysis ID
            analysis_id = extract_id_from_link(link, r'id=(\d+)')
            if not analysis_id:
                continue

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
            # Append the analysis data to the result list
            result["analyses"].append(analysis_data)
        # Return the parsed result
        return result

    except Exception as e:
        logger.error(f"Error parsing analyses data: {e}")
        return {"patient_name": "", "patient_id": "", "analyses": []}



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
            patient_id = extract_id_from_link(patient_link)
            if patient_id:
                checkout_data["patient_id"] = patient_id.strip()

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
        checkout_data["epicrisis"] = extract_textarea_after_label(soup, r'Epicriza[^:]*:')

        # Extract diagnostic (textarea after 'Diagnostic externare')
        checkout_data["diagnostic"] = extract_textarea_after_label(soup, r'Diagnostic externare[^:]*:')

        # Extract surgery (textarea after 'Protocol operator:')
        checkout_data["surgery"] = extract_textarea_after_label(soup, r'Protocol operator[^:]*:')

        # Extract recommendations (textarea after 'Recomandari')
        checkout_data["recommendations"] = extract_textarea_after_label(soup, r'Recomandari[^:]*:')

        return checkout_data
    except Exception as e:
        logger.error(f"Error parsing checkout data: {e}")
        return {}

@require_auth
async def get_service_request(request):
    """Retrieve service request information by ID.

    Gets service request information from the Hipocrate service and parses
    the medical data into structured format.

    Args:
        request: The incoming HTTP request with 'id' path parameter for service request ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with service request data or error information

    See:
        https://build.fhir.org/servicerequest.html
    """
    # Extract service request ID from path
    id = request.match_info.get('id')
    if not id:
        return create_error_response("Service request ID is required")
    logger.info(f"Retrieving service request with ID: {id}")

    # Get credentials from request (added by decorator)
    username, password = request.auth_credentials

    # Create a new HipocrateClient instance with credentials
    client = HipocrateClient(SERVICE_URL, username, password)

    try:
        # The service request endpoint
        request_url = f"/Analyse/LabRequest/buletinRecoltari.asp?id={id}"

        # Retrieve the page
        response_text, success, error_response = await client.get_page(request_url)

        # Check for errors in the response
        if not success:
            return error_response

        # Parse the service request data from HTML content
        request_data = parse_request_data(response_text)
        
        # Create FHIR ServiceRequest resource from parsed data
        fhir_response = create_fhir_service_request(request_data, id, request)
        return web.json_response(fhir_response)

    except Exception as e:
        return create_error_response("Service request retrieval failed", 500, {"exception": str(e)})

def parse_request_data(html_content: str) -> Dict[str, Any]:
    """Parse HTML service request content and extract structured data.

    Extracts patient information and medical data from service request HTML content.

    Args:
        html_content: HTML content of the service request page

    Returns:
        Dictionary containing parsed service request data
    """
    try:
        # Parse HTML content
        soup = BeautifulSoup(html_content, 'html.parser')

        # Initialize result dictionary
        request_data = {
            "patient_name": "",
            "patient_id": "",
            "physician": "",
            "admission_id": "",
            "diagnosis": "",
            "clinical_comments": "",
            "lab_comments": "",
            "procedures": {},
            "request_datetime": "",
            "is_urgent": "~URGENTA~" in html_content
        }

        # Extract patient name
        request_data["patient_name"] = extract_text_after_label(soup, r'Nume Pacient:')

        # Extract patient ID
        patient_link = soup.find('a', href=re.compile(r'../Pacient/edit\.asp\?id='))
        if patient_link:
            request_data["patient_id"] = extract_id_from_link(patient_link)

        # Extract physician
        request_data["physician"] = extract_text_after_label(soup, r'Medicul:', stop_at=r'-')

        # Extract admission ID from the "Back" link
        admission_ids = extract_ids_from_links(soup, r'/checkin\.asp\?id=([^&"]+)')
        if admission_ids:
            request_data["admission_id"] = admission_ids[0]

        # Extract diagnosis
        request_data["diagnosis"] = extract_text_after_label(soup, r'Diagnostic:', 'td')

        # Extract comments (clinical and lab)
        comment_headers = soup.find_all('td', class_='tdnplus', string=re.compile(r'Comentariile', re.IGNORECASE))
        if len(comment_headers) >= 2:
            # Get the next row which contains the actual comments
            comment_row = comment_headers[0].parent.find_next_sibling('tr')
            if comment_row:
                comment_tds = comment_row.find_all('td', class_='tdn')
                if len(comment_tds) >= 2:
                    request_data["clinical_comments"] = comment_tds[0].get_text().strip()
                    request_data["lab_comments"] = comment_tds[1].get_text().strip()

        # Extract procedures from the table
        procedure_rows = soup.find_all('tr')
        for row in procedure_rows:
            cells = row.find_all('td')
            if len(cells) >= 3:
                # Check if this is a procedure row (has numbering in first cell)
                first_cell_text = cells[0].get_text().strip()
                if first_cell_text and first_cell_text.isdigit():
                    procedure_text = cells[1].get_text().strip()
                    if procedure_text:
                        request_data["procedures"][first_cell_text] = procedure_text

        # Extract request datetime (Data si ora cererii)
        request_data["request_datetime"] = extract_text_after_label(soup, r'Data si ora cererii:', stop_at=r'Receptionat')

        return request_data
    except Exception as e:
        logger.error(f"Error parsing service request data: {e}")
        return {}

def create_fhir_service_request(request_data: Dict[str, Any], service_request_id: str, http_request) -> Dict[str, Any]:
    """Convert parsed service request data to FHIR ServiceRequest resource.

    Args:
        request_data: Parsed service request data from parse_request_data
        service_request_id: The ID of the service request
        http_request: The HTTP request object to get the host

    Returns:
        FHIR ServiceRequest resource
    """
    try:
        # Create FHIR ServiceRequest resource using the FHIR class
        fhir_service_request = FHIRServiceRequest(
            id=service_request_id,
            status="active",
            intent="order",
            priority="urgent" if request_data.get("is_urgent", False) else "routine"
        )

        # Create subject reference
        subject = Reference(
            reference=f"Patient/{request_data.get('patient_id', '')}"
        )

        # Add patient name to subject if available
        if request_data.get("patient_name"):
            subject["display"] = request_data["patient_name"]
        fhir_service_request["subject"] = subject

        # Create codeable concept for the service type
        code = CodeableConcept(
            coding=[{
                "system": f"{http_request.scheme}://{http_request.host}/fhir/CodeSystem/service-types",
                "code": "imaging-study",
                "display": "Imaging Study"
            }],
            text="Imaging Study Request"
        )
        fhir_service_request["code"] = code

        # Add requester if available (requesting doctor)
        if request_data.get("physician"):
            fhir_service_request["requester"] = Reference(display=request_data["physician"])

        # Add encounter if we can derive it
        if request_data.get("admission_id"):
            fhir_service_request["encounter"] = Reference(
                reference=f"Encounter/{request_data['admission_id']}"
            )

        # Add reason code if diagnosis is available
        if request_data.get("diagnosis"):
            diagnosis = request_data["diagnosis"]
            # Try to extract ICD-10 code from the diagnosis text
            # Format is usually "CODE Description"
            diagnosis_match = re.match(r'^(\d{3,4})\s+(.+)$', diagnosis)
            if diagnosis_match:
                condition = Reference(
                    reference=f"Condition/{diagnosis_match.group(1)}",
                    display=diagnosis_match.group(2)
                )
            else:
                # If no code found, use the entire diagnosis as display text
                condition = Reference(display=diagnosis)
            fhir_service_request["reason"] = [condition]

        # Add reason reference if clinical comments are available
        if request_data.get("clinical_comments"):
            fhir_service_request["supportingInfo"] = [{
                "display": request_data["clinical_comments"]
            }]

        # Add note for lab comments
        if request_data.get("lab_comments"):
            fhir_service_request["note"] = [{
                "text": request_data["lab_comments"]
            }]

        # Add order details for procedures
        if request_data.get("procedures"):
            procedures = request_data["procedures"]
            order_details = []
            for code, description in procedures.items():
                order_detail = CodeableConcept(
                    coding=[{
                        "system": f"{http_request.scheme}://{http_request.host}/fhir/CodeSystem/procedure-codes",
                        "code": f"procedure-{code}",
                        "display": description
                    }],
                    text=description
                )
                order_details.append(order_detail)
            fhir_service_request["orderDetail"] = order_details

        # Add authoredOn if request datetime is available
        if request_data.get("request_datetime"):
            request_datetime = request_data["request_datetime"]
            # Parse the datetime using our parse_date_time function
            parsed_dt = parse_date_time(request_datetime)
            if parsed_dt:
                # Convert to ISO format
                fhir_service_request["authoredOn"] = parsed_dt.isoformat()
            else:
                # If parsing fails, keep the original string
                fhir_service_request["authoredOn"] = request_datetime

        return fhir_service_request.to_dict()
    except Exception as e:
        logger.error(f"Error converting service request data: {e}")
        return {}


@require_auth
async def get_encounter(request):
    """Retrieve encounter information by ID.

    Gets encounter information from the Hipocrate service and parses
    the medical data into structured format.

    Args:
        request: The incoming HTTP request with 'identifier' query parameter for encounter ID
                 and basic auth credentials for authentication

    Returns:
        JSON response with encounter data or error information

    See:
        https://build.fhir.org/encounter.html
    """
    # Extract encounter ID from path
    id = request.match_info.get('id')
    if not id:
        return create_error_response("Encounter ID is required")
    logger.info(f"Retrieving encounter with ID: {id}")

    # Get credentials from request (added by decorator)
    username, password = request.auth_credentials

    # Create a new HipocrateClient instance with credentials
    client = HipocrateClient(SERVICE_URL, username, password)

    try:
        # The checkout endpoint
        checkout_url = f"/files/checkout.asp?id={id}"
        
        # Retrieve the page
        response_text, success, error_response = await client.get_page(checkout_url)

        # Check for errors in the response
        if not success:
            return error_response

        # Parse the checkout data
        parsed_data = parse_checkout_data(response_text)

        # Convert parsed data to FHIR Encounter resource
        fhir_response = create_fhir_encounter(parsed_data, id, request)
        return web.json_response(fhir_response)

    except Exception as e:
        return create_error_response("Encounter retrieval failed", 500, {"exception": str(e)})


def create_fhir_encounter(parsed_data: Dict[str, Any], encounter_id: str, request) -> Dict[str, Any]:
    """Convert parsed checkout data to FHIR Encounter resource.

    Args:
        parsed_data: Parsed checkout data from parse_checkout_data
        encounter_id: The ID of the encounter
        request: The HTTP request object to get the host

    Returns:
        FHIR Encounter resource
    """
    # Create enhanced FHIR Encounter resource
    fhir_encounter = {
        "resourceType": "Encounter",
        "id": encounter_id,
        "status": "discharged",
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
    if parsed_data.get("performer"):
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
                "display": parsed_data["performer"]
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
        #fhir_encounter["text"] = {
        #    "status": "generated",
        #    "div": f"<div xmlns=\"http://www.w3.org/1999/xhtml\">{parsed_data['epicrisis']}</div>"
        #}

        # Also add as a note
        fhir_encounter["note"] = [
            {
                "text": parsed_data["epicrisis"]
            }
        ]

    # Add diagnosis if available
    if parsed_data.get("admission_diagnostic"):
        fhir_encounter["diagnosis"] = [
            {
                "condition": {
                    "reference": f"Condition/admission-{encounter_id}",
                    "display": parsed_data["admission_diagnostic"]
                },
                "use": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/diagnosis-role",
                            "code": "AD",
                            "display": "Admission diagnosis"
                        }
                    ]
                }
            }
        ]

    # Add discharge diagnosis if available
    if parsed_data.get("diagnostic"):
        if "diagnosis" not in fhir_encounter:
            fhir_encounter["diagnosis"] = []
        fhir_encounter["diagnosis"].append(
            {
                "condition": {
                    "reference": f"Condition/discharge-{encounter_id}",
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
        )

    return fhir_encounter


async def serve_analysis_types(request):
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
        "url": f"{request.scheme}://{request.host}/fhir/CodeSystem/analysis-types",
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


async def serve_spec(request):
    """Serve the OpenAPI specification.

    Returns the OpenAPI specification in JSON format for API documentation.

    Args:
        request: The incoming HTTP request

    Returns:
        JSON response with OpenAPI specification
    """
    logger.info("GET /fhir/spec endpoint accessed")

    try:
        with open('spec.json', 'r') as f:
            spec = json.load(f)
        # Update the server URL with the current PORT
        spec["servers"][0]["url"] = f"{request.scheme}://{request.host}"
        return web.json_response(spec)
    except FileNotFoundError:
        return create_error_response("Specification file not found", 500)
    except json.JSONDecodeError as e:
        return create_error_response("Error parsing specification file", 500)


async def serve_metadata(request):
    """Serve the FHIR capability statement.

    Returns the FHIR capability statement as a metadata endpoint.

    Args:
        request: The incoming HTTP request

    Returns:
        JSON response with FHIR capability statement
    """
    logger.info("GET /fhir/Metadata endpoint accessed")

    # Create a basic FHIR CapabilityStatement
    capability_statement = {
        "resourceType": "CapabilityStatement",
        "id": "hippobridge-fhir-capability-statement",
        "url": f"{request.scheme}://{request.host}/fhir/Metadata",
        "version": "1.0.0",
        "name": "HippoBridgeFHIRCapabilityStatement",
        "title": "HippoBridge FHIR Capability Statement",
        "status": "active",
        "experimental": False,
        "date": datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        "publisher": "HippoBridge",
        "description": "This is the FHIR capability statement for the HippoBridge FHIR API",
        "kind": "instance",
        "software": {
            "name": "HippoBridge",
            "version": "1.0.0"
        },
        "fhirVersion": "4.0.1",
        "format": ["application/fhir+json", "application/json"],
        "rest": [
            {
                "mode": "server",
                "resource": [
                    {
                        "type": "Patient",
                        "interaction": [
                            {"code": "read"},
                            {"code": "search-type"}
                        ]
                    },
                    {
                        "type": "Observation",
                        "interaction": [
                            {"code": "read"},
                            {"code": "search-type"}
                        ]
                    },
                    {
                        "type": "DiagnosticReport",
                        "interaction": [
                            {"code": "read"}
                        ]
                    },
                    {
                        "type": "ImagingStudy",
                        "interaction": [
                            {"code": "read"}
                        ]
                    },
                    {
                        "type": "Encounter",
                        "interaction": [
                            {"code": "read"}
                        ]
                    }
                ]
            }
        ]
    }

    return web.json_response(capability_statement)





def parse_date_time(date_str: str) -> Optional[datetime]:
    """Parse a date string in the format '30 Aug 2025 19:25:00'.

    Args:
        date_str: Date string to parse

    Returns:
        datetime object if parsing successful, None otherwise
    """
    try:
        # Handle common date formats like "30 Aug 2025 19:25:00"
        # Create a mapping for month abbreviations to numbers
        month_mapping = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12,
            'Ian': 1, 'Mai': 5, 'Iun': 6, 'Iul': 7  # Romanian month abbreviations
        }

        # Split the date string into components
        parts = date_str.strip().split()
        if len(parts) != 4:
            return None

        day = int(parts[0])
        month_abbr = parts[1]
        year = int(parts[2])
        time_part = parts[3]

        # Get month number from mapping
        if month_abbr not in month_mapping:
            return None
        month = month_mapping[month_abbr]

        # Parse time
        time_parts = time_part.split(':')
        if len(time_parts) == 2:
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            second = 0
        elif len(time_parts) == 3:
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            second = int(time_parts[2])
        else:
            return None

        # Create datetime object
        return datetime(year, month, day, hour, minute, second)
    except (ValueError, IndexError, TypeError):
        # If parsing fails, return None
        return None

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
        # Parse the HTML content
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

    # Line breaks (single newlines within paragraphs, but not between block elements)
    # Split by block elements to avoid adding <br> between them
    parts = re.split(r'(<(?:h[1-6]|ul|ol|li|p)[^>]*>.*?</(?:h[1-6]|ul|ol|li|p)>)', html, flags=re.DOTALL)
    for i, part in enumerate(parts):
        # Only add <br> tags within paragraph content (not between block elements)
        if not re.match(r'^<(?:h[1-6]|ul|ol|li|p)[^>]*>.*</(?:h[1-6]|ul|ol|li|p)>$', part.strip()):
            # Replace single newlines with <br> but preserve paragraph breaks
            part = re.sub(r'([^\n])\n([^\n])', r'\1<br>\2', part)
            parts[i] = part
    html = ''.join(parts)

    return html

async def serve_md2html(request):
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
        return create_error_response("Invalid JSON data")
    except Exception as e:
        return create_error_response("Markdown conversion failed", 500, {"exception": str(e)})


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
            - age: int - patient age in years
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

    # Calculate age
    today = datetime.today()
    age = today.year - birth_date.year
    # Adjust if birthday hasn't occurred this year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1

    return {
        "valid": True,
        "gender": gender,
        "birth_date": birth_date.strftime('%Y-%m-%d'),
        "age": age,
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

@require_auth
async def serve_validate_cnp(request):
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



@require_auth
async def serve_web_page(request):
    """Handle requests to the root endpoint.

    Returns a web page with a CNP input form and analysis functionality.
    Requires basic authentication.

    Args:
        request: The incoming HTTP request

    Returns:
        HTML response with the web interface or 401 if not authenticated
    """
    logger.info("Root endpoint accessed")

    # Get credentials from request (added by decorator)
    username, password = request.auth_credentials

    # Try to login with provided credentials
    client = HipocrateClient(SERVICE_URL, username, password)
    session, login_success = await client.get_authenticated_session(username, password)

    if not login_success:
        return web.Response(status=401, headers={'WWW-Authenticate': 'Basic realm="HippoBridge"'})

    # Set cookie with 30-minute expiration
    response = web.StreamResponse()
    response.set_cookie('auth_user', username, max_age=1800, httponly=True)

    # Serve the external HTML file
    with open('static/main.html', 'r') as f:
        html_content = f.read()

    response.content_type = 'text/html'
    await response.prepare(request)
    await response.write(html_content.encode('utf-8'))
    return response



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

def create_error_response(message: str, status_code: int = 400, details: Dict[str, Any] = None) -> web.Response:
    """Create a standardized error response.

    Args:
        message: Error message
        status_code: HTTP status code (default: 400)
        details: Additional error details

    Returns:
        Standardized JSON error response
    """
    if status_code >= 500:
        logger.error(f"{message}")
    else:
        logger.warning(f"{message}")
    # Build response data
    response_data = {
        "status": "error",
        "message": message
    }
    # Include additional details if provided
    if details:
        response_data["details"] = details
    # Return JSON response with appropriate status code
    return web.json_response(response_data, status=status_code)


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

async def on_startup(app):
    """Handle application startup.

    Args:
        app: The web application
    """
    logger.info("Application startup")

async def on_cleanup(app):
    """Handle application cleanup.

    Closes all user HTTP sessions.

    Args:
        app: The web application
    """
    logger.info("Application cleanup")
    await user_session_manager.close_all_sessions()

async def auth_middleware(app, handler):
    """Authentication middleware that skips static files.
    
    Args:
        app: The web application
        handler: The request handler

    Returns:
        Middleware handler
    """
    async def middleware_handler(request):
        # Skip authentication for static files
        if request.path.startswith('/static/'):
            return await handler(request)
        # Apply authentication for other requests
        return await handler(request)
    # Return the middleware handler
    return middleware_handler

async def init_app():
    """Initialize the web application.

    Sets up routes and application lifecycle handlers.

    Returns:
        Configured web application
    """
    logger.info("Initializing web application")

    app = web.Application(middlewares=[auth_middleware])
    app.router.add_get('/', serve_web_page)
    # FHIR-compatible endpoints
    app.router.add_get('/fhir/Patient', search_patient)
    app.router.add_get('/fhir/Patient/{id}', get_patient)
    app.router.add_get('/fhir/DiagnosticReport/{id}', get_diagnostic_report)
    app.router.add_get('/fhir/ImagingStudy/{id}', get_imaging_study)
    app.router.add_get('/fhir/Encounter/{id}', get_encounter)
    app.router.add_get('/fhir/Observation', search_observation)
    app.router.add_get('/fhir/Observation/{id}', get_observation)
    app.router.add_get('/fhir/ServiceRequest/{id}', get_service_request)
    app.router.add_get('/fhir/ValueSet/cnp', serve_validate_cnp)
    app.router.add_post('/fhir/md2html', serve_md2html)
    app.router.add_get('/fhir/CodeSystem/analysis-types', serve_analysis_types)
    app.router.add_get('/fhir/spec', serve_spec)
    app.router.add_get('/fhir/Metadata', serve_metadata)
    app.router.add_static('/static/', path='static', name='static')

    # Setup startup and cleanup
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # Return the configured app
    return app

# Load configuration
config = load_config()

# Configuration values
SERVICE_URL = config.get('hipocrate', 'service_url')
PORT = config.getint('server', 'port')
HOST = config.get('server', 'host')

# Run the application
if __name__ == "__main__":
    logger.info(f"Starting HippoBridge server on {HOST}:{PORT}")
    app = init_app()
    web.run_app(app, host=HOST, port=PORT)
