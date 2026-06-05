#!/usr/bin/env python3
"""Hipocrate medical system data retrieval client implementation.

Copyright (C) 2025 Costin Stroie <costinstroie@eridu.eu.org>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

This module provides client classes for interacting with the Hipocrate medical system,
a web-based medical record management system. It includes specialized clients for
different types of medical data retrieval and parsing, with support for authentication,
caching, and FHIR-compatible data formatting.

Key features:
- HipoClient: Base client for general Hipocrate service interactions
- HipoClientPatient: Specialized client for patient data
- HipoClientPatientSearch: Specialized client for patient search operations
- HipoClientCheckout: Specialized client for patient discharge/checkout data
- HipoClientServiceRequest: Specialized client for medical service requests
- HipoClientServiceRequestSearch: Specialized client for service request search operations
- HipoClientImagingStudy: Specialized client for imaging study data
- HipoClientDiagnosticReport: Specialized client for diagnostic report data
- Automatic session management with cookie handling
- Response caching with LRU eviction and timeout
- FHIR-compatible data structure conversion
- Robust error handling and logging

The module handles the complexities of web scraping medical data including:
- Authentication and session management
- Redirect following and form submission
- HTML parsing and data extraction
- Character encoding handling
- Data validation and normalization
"""

import aiohttp
from aiohttp import web
from yarl import URL
import logging
import re
from bs4 import BeautifulSoup, Comment
import html
from datetime import datetime, timedelta
import configparser

from typing import Any, Dict, List, Optional, Tuple, Union

from extractors import extract_id_from_link, extract_ids_from_links, extract_text_ids_from_links, extract_selected_from_dropdown, extract_text_after_label, extract_text_from_element, extract_textarea_after_label, extract_value_from_input
from extractors import parse_cnp, parse_date_time
from urlcache import URLCache
import asyncio

from markdown import html_to_markdown

# Import FHIR classes
from fhir import ServiceRequest as FHIRServiceRequest
from fhir import CodeableConcept as FHIRCodeableConcept
from fhir import Reference as FHIRReference
from fhir import Patient as FHIRPatient
from fhir import OperationOutcome as FHIROperationOutcome
from fhir import ImagingStudy as FHIRImagingStudy
from fhir import DiagnosticReport as FHIRDiagnosticReport
from fhir import Encounter as FHIREncounter
from fhir import Bundle as FHIRBundle

# Import HipoData class
from hipodata import HipoData

logger = logging.getLogger('HipoClient')



# Analysis types dictionary for reuse across functions
ANALYSIS_TYPES = {
    "radio": {
        "display": "Radiology",
        "definition": "Radiology",
        "domain": 36
    },
    "ct": {
        "display": "CT Scan",
        "definition": "Computed Tomography",
        "domain": 32
    },
    "irm": {
        "display": "MRI",
        "definition": "Magnetic Resonance Imaging",
        "domain": 34
    },
    "eco": {
        "display": "Ultrasound",
        "definition": "Echography",
        "domain": 33
    },
    "lab": {
        "display": "Laboratory",
        "definition": "Laboratory tests",
        "domain": 0
    },
    "lac": {
        "display": "Angiography and Cardiac Catheterization",
        "definition": "Angiography and Cardiac Catheterization",
        "domain": 0
    },
    "lii": {
        "display": "Interventional Radiology",
        "definition": "Interventional Radiology",
        "domain": 0
    },
    "rads": {
        "display": "Fluoroscopy and CEUS",
        "definition": "Fluoroscopy and Contrast-Enhanced Ultrasound",
        "domain": 37
    },
    "apa": {
        "display": "Anatomopathology",
        "definition": "Anatomopathology",
        "domain": 0
    }
}




# Load region identification rules from config file
def load_region_rules():
    """Load region identification rules from regions.cfg file."""
    config = configparser.ConfigParser()
    config.read('regions.cfg')
    
    radio_rules = {}
    eco_rules = {}
    ct_rules = {}
    mri_rules = {}
    
    if 'radiography' in config:
        for key in config['radiography']:
            radio_rules[key] = [word.strip() for word in config['radiography'][key].split(',')]
    
    if 'ultrasound' in config:
        for key in config['ultrasound']:
            eco_rules[key] = [word.strip() for word in config['ultrasound'][key].split(',')]
    
    if 'ct' in config:
        for key in config['ct']:
            ct_rules[key] = [word.strip() for word in config['ct'][key].split(',')]
    
    if 'mri' in config:
        for key in config['mri']:
            mri_rules[key] = [word.strip() for word in config['mri'][key].split(',')]
    
    return radio_rules, eco_rules, ct_rules, mri_rules

# Load the region rules
RADIO_REGION_RULES, ECO_REGION_RULES, CT_REGION_RULES, MRI_REGION_RULES = load_region_rules()






# Maps internal study-type codes → DICOM modality (code, display)
DICOM_MODALITY = {
    "radio": ("CR",  "Computed Radiography"),
    "eco":   ("US",  "Ultrasound"),
    "ct":    ("CT",  "Computed Tomography"),
    "mri":   ("MR",  "Magnetic Resonance"),
    "other": ("OT",  "Other"),
}

# Headers for compatibility with Hipocrate service
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ro-RO,ro;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


def identify_study_type_and_region(desc: str) -> Tuple[str, str]:
    """
    Identify the study type and anatomical region from the study description.

    Args:
        desc: Study description text

    Returns:
        tuple: (study_type, region) where study_type is 'radio', 'eco' or 'other'
               and region is the identified anatomical region or 'unknown'
    """
    if not desc:
        return 'other', 'unknown'
    
    desc_lower = desc.strip().lower()
    
    # Check if it's an MRI study (contains REZONANTA MAGNETICA)
    if 'rezonanta' in desc_lower:
        study_type = 'mri'
        region_rules = MRI_REGION_RULES
    # Check if it's a CT study (contains TOMOGRAFIA COMPUTERIZATA)
    elif desc_lower.startswith('tomografia') or \
         desc_lower.startswith('angiotomografia') or \
         desc_lower.startswith('densitometria'):
        study_type = 'ct'
        region_rules = CT_REGION_RULES
    # Check if it's a radiography study (starts with RADIOGRAFIA or RADIO)
    elif desc_lower.startswith('radiografia'):
        study_type = 'radio'
        region_rules = RADIO_REGION_RULES
    # Check if it's an ultrasound study (starts with ECOGRAFIA, ULTRASONOGRAFIA, or ECO)
    elif desc_lower.startswith('ecografia') or desc_lower.startswith('ultrasonografia'):
        study_type = 'eco'
        region_rules = ECO_REGION_RULES
    else:
        study_type = 'other'
        region_rules = {}
    
    # Identify region based on keywords
    region = 'unknown'
    for region_key, keywords in region_rules.items():
        if any(i in desc_lower for i in keywords):
            region = region_key
            break
    
    return study_type, region



# Simple in-memory cache for HTTP responses (imported from urlcache module)
url_cache = URLCache(max_size=500, timeout=30 * 60)

# Global semaphore: cap total concurrent outbound requests to Hipocrate
_hipocrate_semaphore = asyncio.Semaphore(6)


class UserSessionManager:
    """Manager for user-specific HTTP sessions with automatic cookie handling.

    Holds one aiohttp.ClientSession per username (for cookie reuse) plus one
    asyncio.Lock per username so that concurrent requests never trigger two
    simultaneous logins for the same user.
    """

    def __init__(self):
        self.user_sessions: Dict[str, aiohttp.ClientSession] = {}
        # Per-user lock: only one login sequence runs at a time per user
        self._login_locks: Dict[str, asyncio.Lock] = {}
        # Track which users have an established Hipocrate session
        self._authenticated: Dict[str, bool] = {}

    def get_user_session(self, username: str) -> aiohttp.ClientSession:
        """Get or create a user-specific aiohttp session with cookie support."""
        if username not in self.user_sessions or self.user_sessions[username].closed:
            logger.debug(f"Creating new session for user {username}")
            self.user_sessions[username] = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
            self._authenticated[username] = False
        return self.user_sessions[username]

    def get_login_lock(self, username: str) -> asyncio.Lock:
        """Return the per-user login lock, creating it on first access."""
        if username not in self._login_locks:
            self._login_locks[username] = asyncio.Lock()
        return self._login_locks[username]

    def is_authenticated(self, username: str) -> bool:
        """Return True if this user has an active Hipocrate session."""
        return self._authenticated.get(username, False)

    def set_authenticated(self, username: str, value: bool) -> None:
        self._authenticated[username] = value

    async def close_all_sessions(self):
        """Close all user sessions and free associated resources."""
        logger.info("Closing all user sessions")
        for username, session in self.user_sessions.items():
            if session and not session.closed:
                logger.debug(f"Closing session for user {username}")
                await session.close()
        self._authenticated.clear()


# Global user session manager instance
user_session_manager = UserSessionManager()


class HipoClient:
    """Base client for interacting with the Hipocrate medical system.

    Provides core functionality for authenticating with the Hipocrate service,
    making HTTP requests, handling sessions, caching responses, and parsing
    medical data from HTML content. This class should be extended for specific
    use cases rather than used directly.
    """

    def __init__(self, service_url: str, request: Optional[web.Request] = None):
        """Initialize the Hipocrate client."""
        self.service_url = service_url
        self.request_url = f"main.asp"
        self.request = request
        self.headers = HEADERS.copy()
        self.url_cache = url_cache
        self.username = None
        self.password = None
        # Get session using the client's session manager
        self.session = None
        
        # Extract credentials from request if provided
        if self.request and 'auth_credentials' in self.request:
            self.username, self.password = self.request['auth_credentials']

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

        Attempts to authenticate with the Hipocrate service using provided
        credentials. Checks if already logged in before attempting login.

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
        """Close all user sessions by delegating to the session manager."""
        await user_session_manager.close_all_sessions()


    def cache_get(self, url: str) -> Optional[str]:
        """Get cached response for URL if exists and not expired.

        Args:
            url: URL to lookup in cache

        Returns:
            Cached response text or None if not found or expired
        """
        return self.url_cache.get(self.get_full_url(url))

    def cache_put(self, url: str, response_text: str) -> None:
        """Add response to cache.

        Args:
            url: URL key for caching
            response_text: Response text to cache
        """
        self.url_cache.put(self.get_full_url(url), response_text)

    def cache_remove(self, url: str):
        """Remove cached response for URL.

        Args:
            url: URL to remove from cache
        """
        return self.url_cache.remove(url)

    def cache_clear(self) -> None:
        """Clear all cache entries."""
        self.url_cache.clear()

    def is_login_page(self, content: str) -> bool:
        """Detect if the provided content is a login page.

        Checks for 'Identificare' in the HTML title or common login form
        elements to determine if we're on the login page.

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

    async def login_if_needed(self, session, username: str, password: str, force: bool = False) -> bool:
        """Ensure the user has an active Hipocrate session, logging in if necessary.

        Uses a per-user lock so that concurrent requests for the same user never
        trigger two simultaneous login sequences. All login HTTP calls go through
        the global semaphore so they count against the concurrency budget.

        Args:
            session: The aiohttp session for this user
            username: Hipocrate username
            password: Hipocrate password
            force: Skip the is-logged-in check and go straight to login.
                   Pass True when the caller already knows the session is expired.

        Returns:
            True if the session is authenticated, False on failure
        """
        if not username or not password:
            logger.warning("Username or password not set, skipping login")
            return False

        login_lock = user_session_manager.get_login_lock(username)

        async with login_lock:
            # Another coroutine may have completed login while we were waiting
            if not force and user_session_manager.is_authenticated(username):
                logger.debug(f"User {username} already authenticated (lock released by peer)")
                return True

            try:
                if not force:
                    # Check whether the existing session is still valid
                    main_url = f"{self.service_url}/main.asp"
                    logger.debug(f"Checking login state for {username}")
                    async with _hipocrate_semaphore:
                        async with session.get(main_url, headers=self.headers) as resp:
                            main_text = await self.handle_response_encoding(resp)
                    if not self.is_login_page(main_text):
                        logger.info(f"User {username} already logged in")
                        user_session_manager.set_authenticated(username, True)
                        return True

                logger.info(f"Logging in user {username}")

                # Grab initial cookies from the default page
                default_url = f"{self.service_url}/default.asp"
                async with _hipocrate_semaphore:
                    async with session.get(default_url, headers=self.headers) as resp:
                        logger.debug(f"Default page status: {resp.status}")

                login_data = {
                    "id_recuperare_pwd_2": "",
                    "strUser": username,
                    "strPwd": password,
                    "cboLang": "ro"
                }
                login_headers = {**self.headers, "Referer": default_url}
                login_url = f"{self.service_url}/security/logon.asp"

                async with _hipocrate_semaphore:
                    async with session.post(login_url, data=login_data, headers=login_headers) as resp:
                        response_text = await self.handle_response_encoding(resp)
                        status = resp.status
                        location = resp.headers.get("Location", "")
                        logger.debug(f"Login response status: {status}")

                success = (status == 302 and "main.asp" in location) or \
                          (not self.is_login_page(response_text))

                if success:
                    logger.info(f"Login successful for user {username}")
                    user_session_manager.set_authenticated(username, True)
                else:
                    logger.warning(f"Login failed for user {username}")
                    user_session_manager.set_authenticated(username, False)

                return success

            except Exception as e:
                logger.error(f"Login error for user {username}: {e}")
                user_session_manager.set_authenticated(username, False)
                return False

    async def make_authenticated_request(self, url, method="GET", data=None, username=None, password=None):
        """Make an authenticated request to the Hipocrate service with automatic login handling.

        Handles the complete request lifecycle including authentication, caching,
        and error handling. Automatically retries requests with re-authentication
        if session expires.

        Args:
            url: The URL to request
            method: HTTP method ("GET" or "POST")
            data: Data to send with POST requests
            username: Username for login if needed
            password: Password for login if needed

        Returns:
            Tuple of (page_content, error_message) where error_message is None if no error
        """

        async def _make_request():
            """Make a single HTTP request and return unescaped response text."""
            if method == "GET":
                logger.debug(f"Making GET request to: {url}")
                async with self.session.get(url, headers=self.headers) as response:
                    response_text = await self.handle_response_encoding(response)
                    logger.debug(f"GET response status: {response.status}")
            else:  # POST
                logger.debug(f"Making POST request to: {url}")
                # Strip Content-Type so aiohttp sets it automatically for form data
                post_headers = {k: v for k, v in self.headers.items() if k != "Content-Type"}
                if data:
                    async with self.session.post(url, data=data, headers=post_headers) as response:
                        response_text = await self.handle_response_encoding(response)
                        logger.debug(f"POST response status: {response.status}")
                else:
                    async with self.session.post(url, headers=post_headers) as response:
                        response_text = await self.handle_response_encoding(response)
                        logger.debug(f"POST response status: {response.status}")
            return html.unescape(response_text)

        # For GET requests: check cache first, then deduplicate in-flight fetches
        if method == "GET":
            cached_response = self.cache_get(url)
            if cached_response is not None:
                return cached_response, None

            # If another coroutine is already fetching this URL, wait for it
            if self.url_cache.is_inflight(url):
                logger.debug(f"Waiting for in-flight request: {url}")
                await self.url_cache.wait_inflight(url)
                # After the wait, the result should be cached
                cached_response = self.cache_get(url)
                if cached_response is not None:
                    return cached_response, None
                # Fell through (fetch failed for the other caller) — try ourselves

            # Mark URL as in-flight before fetching
            inflight_event = self.url_cache.mark_inflight(url)

        try:
            # Limit concurrent outbound requests to Hipocrate
            async with _hipocrate_semaphore:
                if self.session.cookie_jar:
                    cookies = self.session.cookie_jar.filter_cookies(URL(self.service_url))
                    logger.debug(f"Using {len(cookies)} cookies for request to {url}")

                response_text = await _make_request()

            # Check if we got redirected to login page (session expired)
            if self.is_login_page(response_text):
                logger.warning(f"Session expired for {username}, re-logging in")
                user_session_manager.set_authenticated(username, False)
                login_success = await self.login_if_needed(self.session, username, password, force=True)
                if login_success:
                    async with _hipocrate_semaphore:
                        response_text = await _make_request()
                    if self.is_login_page(response_text):
                        if method == "GET":
                            self.url_cache.resolve_inflight(url)
                        return None, "Authentication failed after retry"
                else:
                    if method == "GET":
                        self.url_cache.resolve_inflight(url)
                    return None, "Re-authentication failed"

            # Cache the response for GET requests and wake up any waiters
            if method == "GET":
                self.cache_put(url, response_text)
                self.url_cache.resolve_inflight(url)

            return response_text, None
        except Exception as e:
            if method == "GET":
                self.url_cache.resolve_inflight(url)
            return None, str(e)

    async def handle_response_encoding(self, response):
        """Handle response encoding for the Hipocrate service.

        Attempts to decode response content with appropriate character encoding,
        falling back to common encodings used by the Hipocrate service if UTF-8 fails.

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

    def is_expected_page(self, soup: BeautifulSoup, expected_title_text: str) -> bool:
        """Check if the parsed HTML content is the expected page by looking for specific text in the title.

        Args:
            soup: BeautifulSoup object of the parsed HTML content
            expected_title_text: Text that should be present in the page title

        Returns:
            True if the page title contains the expected text, False otherwise
        """
        title = soup.find('title')
        return title and expected_title_text in title.get_text()

    def get_full_url(self, url: str) -> str:
        """Construct full URL from service URL and relative path.

        Args:
            url: Relative path or full URL

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

    def get_title(self, soup: BeautifulSoup) -> str:
        """Extract the title from a BeautifulSoup object.

        Args:
            soup: BeautifulSoup object to extract title from

        Returns:
            Title text or empty string if not found
        """
        try:
            title_tag = soup.find('title')
            if title_tag:
                return title_tag.get_text().strip()
            return ""
        except Exception as e:
            logger.error(f"Error extracting title: {e}")
            return ""

    def get_error(self, soup: BeautifulSoup) -> str:
        """Extract error message from a BeautifulSoup object.

        Args:
            soup: BeautifulSoup object to extract error message from

        Returns:
            Error message text or empty string if not found
        """
        try:
            error_div = soup.find('div', id='divError')
            if error_div:
                # Get the first child div which contains the actual error/success message
                first_child_div = error_div.find('div')
                if first_child_div:
                    return first_child_div.get_text().strip()
                # Fallback to getting text from the parent div
                return error_div.get_text().strip()
            return ""
        except Exception as e:
            logger.error(f"Error extracting error message: {e}")
            return ""

    async def post_form(self, url, data=None):
        """Submit a form to Hipocrate. Returns (page_content, error_message)."""
        current_url = self.get_full_url(url)

        if not self.session:
            self.session = self.get_user_session(self.username)

        start_time = datetime.now()
        response_text, error_response = await self.make_authenticated_request(
            current_url, "POST", data, self.username, self.password
        )
        duration = (datetime.now() - start_time).total_seconds()

        if error_response:
            error_msg = error_response.get("message", "Unknown error") if isinstance(error_response, dict) else str(error_response)
            logger.warning(f"POST failed in {duration:.2f}s: {error_msg}")
            return None, error_msg
        logger.info(f"Response received in {duration:.2f}s")
        return response_text, None

    async def get_page(self, url, max_redirects=5):
        """Retrieve a Hipocrate page with auth and caching. Returns (page_content, error_message).

        aiohttp follows redirects automatically; max_redirects is unused but kept for API compat.
        """
        current_url = self.get_full_url(url)

        if not self.session:
            self.session = self.get_user_session(self.username)

        start_time = datetime.now()
        response_text, error_response = await self.make_authenticated_request(
            current_url, "GET", None, self.username, self.password
        )
        duration = (datetime.now() - start_time).total_seconds()

        if error_response:
            error_msg = error_response.get("message", "Unknown error") if isinstance(error_response, dict) else str(error_response)
            logger.warning(f"GET failed in {duration:.2f}s: {current_url}: {error_msg}")
            return None, error_msg

        logger.info(f"Page retrieved in {duration:.2f}s: {current_url}")
        return response_text, None

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        """Override in subclasses to parse Hipocrate HTML into HipoData."""
        return HipoData(status="error", message="No data")

    def fhir_response(self, parsed_data: HipoData, **kwargs) -> FHIROperationOutcome:
        """Override in subclasses to convert HipoData to a FHIR resource."""
        return FHIROperationOutcome.from_error(
            message="No data",
            code="not-supported",
            severity="error"
        )

    async def fetch_and_parse(self, *args, max_redirects=5, **kwargs):
        """Fetch request_url (formatted with kwargs) and return parsed HipoData."""
        data = HipoData(status="success", message="")
        url = self.request_url.format(**kwargs)
        try:
            response_text, error_message = await self.get_page(url, max_redirects)
            if error_message:
                data.set_error(error_message)
                return data
            return self.parse_data(response_text, **kwargs)
        except Exception as e:
            logger.error(f"fetch_and_parse failed: {e}")
            data.set_error(f"Data retrieval failed: {e}")
            return data

    async def fetch_respond_fhir(self, *args, max_redirects=5, **kwargs):
        """Fetch, parse, and convert to FHIR. Returns resource or OperationOutcome."""
        try:
            parsed_data = await self.fetch_and_parse(**kwargs)
            if parsed_data.get("status") == "error":
                return FHIROperationOutcome.from_error(
                    message=parsed_data.get("message", "Unknown error"),
                    code="processing",
                    severity="error"
                )
            return self.fhir_response(parsed_data, **kwargs)
        except Exception as e:
            logger.error(f"Data retrieval failed: {str(e)}")
            return FHIROperationOutcome.from_exception(e, code="exception")

    async def debug_page(self, *args, max_redirects=5, **kwargs):
        """Return raw Hipocrate HTML for the request URL (used by ?debug=page)."""
        url = self.request_url.format(**kwargs)
        try:
            response_text, error_message = await self.get_page(url, max_redirects)
            if error_message:
                return f"Page error: {error_message}"
            return response_text
        except Exception as e:
            return f"Page retrieval failed: {str(e)}"



class HipoClientPatient(HipoClient):
    """Specialized client for patient related operations in the Hipocrate medical system.

    Handles retrieval and parsing of patient information including personal data,
    contact information, medical identifiers, and related encounter IDs.
    """

    def __init__(self, service_url: Optional[str] = None, request: Optional[web.Request] = None):
        super().__init__(service_url=service_url, request=request)
        self.request_url = "/Pacient/edit.asp?id={id}"

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        """Parse a Hipocrate patient page into HipoData (patient, presentation, checkin, checkout)."""
        data = HipoData(status="success")

        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            if not self.is_expected_page(soup, 'Date pasaportale'):
                # Log snippet of response for debugging
                data.set_error(f"Unexpected page for Patient: {self.get_title(soup)}")
                logger.warning(f"{data['message']}: {self.get_error(soup)}")
                return data

            # Check if there is patient data on page by getting the name from the div with id "div_navbar"
            patient_name_from_navbar = extract_text_from_element(soup, element_id='div_navbar')
            if not patient_name_from_navbar:
                data.set_error("Patient name from navbar is empty, invalid patient id")
                return data

            data.store("patient.name", patient_name_from_navbar)

            data.store("patient.family_name", extract_value_from_input(soup, element_id="strNume"))
            data.store("patient.given_name", extract_value_from_input(soup, element_id="strPrenume"))
            if data.get("patient.family_name") and data.get("patient.given_name"):
                data.store("patient.name", f"{data.get('patient.family_name')} {data.get('patient.given_name')}")

            data.store("patient.cnp", extract_value_from_input(soup, element_id="strCNP"))
            data.store("patient.id", extract_value_from_input(soup, element_id="hdnCodeID"))
            data.store("patient.cid", extract_value_from_input(soup, element_id="strCID"))
            data.store("patient.phone", extract_value_from_input(soup, element_id="strTelefon"))
            data.store("patient.email", extract_value_from_input(soup, element_id="strEmail"))
            data.store("patient.weight", extract_value_from_input(soup, element_id="strGreutate"))
            data.store("patient.height", extract_value_from_input(soup, element_id="strInaltime"))
            data.store("patient.mcp", extract_value_from_input(soup, element_id="strmcp"))
            data.store("patient.address", extract_selected_from_dropdown(soup, element_id='strDomLegal_LocId'))

            if data.get("patient.cnp"):
                parsed_cnp = parse_cnp(data.get("patient.cnp"))
                if parsed_cnp.get("valid"):
                    data.store("patient.sex", parsed_cnp.get("gender", "unknown"))
                    data.store("patient.birth_date", parsed_cnp.get("birth_date", ""))

            # Fallback: Hipocrate stores birth date as DD/MM/YYYY in strDataNastere
            if not data.get("patient.birth_date"):
                birth_date = extract_value_from_input(soup, element_id='strDataNastere')
                if birth_date and re.match(r'\d{2}/\d{2}/\d{4}', birth_date):
                    try:
                        day, month, year = birth_date.split('/')
                        data.store("patient.birth_date", f"{year}-{month}-{day}")
                    except Exception:
                        pass

            data.store_list("presentation", extract_ids_from_links(soup, r'../files/presentation\.asp\?id=(\d+)'))
            data.store_list("checkin", extract_ids_from_links(soup, r'../files/checkin\.asp\?id=(\d+)'))
            data.store_list("checkout", extract_ids_from_links(soup, r'../files/checkout\.asp\?id=(\d+)'))

            return data

        except Exception as e:
            logger.error(f"Error parsing patient data: {e}")
            data.set_error(str(e))
            return data

    def fhir_response(self, parsed_data: HipoData, **kwargs) -> Union[FHIRPatient, FHIROperationOutcome]:
        """Convert parsed patient HipoData to a FHIR Patient resource."""
        http_request = kwargs.get('http_request', self.request)
        patient_id = kwargs.get('id', '')

        try:
            if parsed_data.get("status") == "error":
                return FHIROperationOutcome.from_error(
                    message=parsed_data.get("message", "Error in parsed patient data"),
                    code="processing",
                    severity="error"
                )

            family_name = parsed_data.get("patient.family_name", "")
            given_names = [parsed_data.get("patient.given_name", "")] if parsed_data.get("patient.given_name") else []

            if not family_name and not given_names:
                name_parts = parsed_data.get("patient.name", "").split()
                family_name = name_parts[0] if len(name_parts) > 0 else ""
                given_names = name_parts[1:] if len(name_parts) > 1 else []

            gender = parsed_data.get("patient.sex", "")
            birth_date = parsed_data.get("patient.birth_date", "")

            fhir_patient = FHIRPatient(
                id=parsed_data.get("patient.id", patient_id),
                active=True,
            )
            if gender:
                fhir_patient["gender"] = gender
            if birth_date:
                fhir_patient["birthDate"] = birth_date

            fhir_patient["name"] = [{
                "use": "official",
                "family": family_name,
                "given": given_names
            }]

            telecom = []
            if parsed_data.get("patient.phone"):
                telecom.append({"system": "phone", "value": parsed_data.get("patient.phone")})
            if parsed_data.get("patient.email"):
                telecom.append({"system": "email", "value": parsed_data.get("patient.email")})
            if telecom:
                fhir_patient["telecom"] = telecom

            if parsed_data.get("patient.address"):
                fhir_patient["address"] = [{"text": parsed_data.get("patient.address")}]

            extensions = []
            if parsed_data.get("patient.weight"):
                extensions.append({
                    "url": "http://hl7.org/fhir/us/vitals/StructureDefinition/body-weight",
                    "valueString": parsed_data.get("patient.weight")
                })
            if parsed_data.get("patient.height"):
                extensions.append({
                    "url": "http://hl7.org/fhir/us/vitals/StructureDefinition/height",
                    "valueString": parsed_data.get("patient.height")
                })

            presentations = parsed_data.get("presentation", [])
            if presentations and http_request:
                extensions.append({
                    "url": f"{http_request.scheme}://{http_request.host}/fhir/StructureDefinition/presentation-ids",
                    "valueString": ",".join(presentations) if isinstance(presentations, list) else str(presentations)
                })
            checkins = parsed_data.get("checkin", [])
            if checkins and http_request:
                extensions.append({
                    "url": f"{http_request.scheme}://{http_request.host}/fhir/StructureDefinition/checkin-ids",
                    "valueString": ",".join(checkins) if isinstance(checkins, list) else str(checkins)
                })
            checkouts = parsed_data.get("checkout", [])
            if checkouts and http_request:
                extensions.append({
                    "url": f"{http_request.scheme}://{http_request.host}/fhir/StructureDefinition/checkout-ids",
                    "valueString": ",".join(checkouts) if isinstance(checkouts, list) else str(checkouts)
                })
            if extensions:
                fhir_patient["extension"] = extensions

            identifiers = []
            if parsed_data.get("patient.cnp") and http_request:
                identifiers.append({
                    "use": "official",
                    "system": f"{http_request.scheme}://{http_request.host}/fhir/NamingSystem/patient-cnp",
                    "value": parsed_data.get("patient.cnp")
                })
            if parsed_data.get("patient.cid") and http_request:
                identifiers.append({
                    "system": f"{http_request.scheme}://{http_request.host}/fhir/NamingSystem/patient-cid",
                    "value": parsed_data.get("patient.cid")
                })
            if parsed_data.get("patient.mcp") and http_request:
                identifiers.append({
                    "system": f"{http_request.scheme}://{http_request.host}/fhir/NamingSystem/patient-mcp",
                    "value": parsed_data.get("patient.mcp")
                })
            if identifiers:
                fhir_patient["identifier"] = identifiers

            return fhir_patient

        except Exception as e:
            logger.error(f"Error converting patient data to FHIR: {e}")
            return FHIROperationOutcome.from_exception(e, code="exception")


class HipoClientPatientSearch(HipoClientPatient):
    """Specialized client for patient search operations in the Hipocrate medical system.

    Handles searching for patients by various criteria including name, CNP (personal identification number),
    partial CNP, and patient code. Supports both single patient and multiple patient result parsing.
    """

    def __init__(self, service_url: Optional[str] = None, request: Optional[web.Request] = None):
        """Initialize the patient search client."""
        super().__init__(service_url=service_url, request=request)
        self.request_url = "/files/search.asp?what=PA"

    async def search(self, search_term: str, **kwargs) -> HipoData:
        """Search for patients by various criteria.

        Handles searching for patients by name, CNP, partial CNP, or patient code.
        Automatically determines the search type based on the input format.

        Args:
            search_term: Search term - can be name, CNP, partial CNP (ending with *), or patient code
            **kwargs: Additional arguments

        Returns:
            HipoData containing search results or error information
        """
        data = HipoData(status="success", message="", patients=[])

        if search_term.isdigit():
            if len(search_term) == 13:
                if parse_cnp(search_term).get("valid", False):
                    logger.info(f"Performing CNP search for: {search_term}")
                else:
                    logger.info(f"Performing patient code search for: {search_term}")
            else:
                logger.info(f"Performing patient code search for: {search_term}")
        else:
            if search_term.endswith('*'):
                prefix = search_term[:-1]
                if prefix.isdigit() and len(prefix) < 13:
                    logger.info(f"Performing partial CNP search for: {search_term}")
                else:
                    logger.info(f"Searching for patients by name: {search_term}")
            else:
                logger.info(f"Searching for patients by name: {search_term}")

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
            "btnCODQR": "IMPORTA COD QR",
            "btnCODQRClear": "STERGE COD QR",
            "hdnQRSave": "",
            "IdQR": ""
        }

        try:
            response_text, error_message = await self.post_form(self.request_url, search_data)

            if error_message:
                data.set_error(error_message)
                return data

            parsed_data = self.parse_one_patient_data(response_text, **kwargs)
            if parsed_data and parsed_data.get("status") == "success":
                return parsed_data
            
            parsed_data = self.parse_multiple_patients_data(response_text, **kwargs)
            if parsed_data and parsed_data.get("status") == "success":
                return parsed_data
            
            data.set_error("Patient not found")
            return data

        except Exception as e:
            data.set_error(f"Patient search failed: {str(e)}")
            return data

    def parse_one_patient_data(self, html_content: str, **kwargs) -> HipoData:
        """Parse a single-patient Hipocrate page (delegates to parse_data)."""
        return self.parse_data(html_content, **kwargs)

    def parse_multiple_patients_data(self, html_content: str) -> HipoData:
        """Parse a multi-patient Hipocrate search results page into HipoData."""
        # Initialize empty dict for patients
        data = HipoData(status="success", message="", patients = {})

        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            if not self.is_expected_page(soup, 'Fisier'):
                # Return empty list if not expected page
                data.set_error(f"Unexpected page for PatientSearch: {self.get_title(soup)}")
                logger.warning(f"{data['message']}: {self.get_error(soup)}")
                return data

            pattern = r"javascript:Edit\('([^']+)'\);"
            data["patients"] = extract_text_ids_from_links(soup, pattern)

        except Exception as e:
            logger.error(f"Error parsing multiple patients data: {e}")
            data.set_error(str(e))

        return data

    def fhir_bundle_response(self, parsed_data: HipoData, **kwargs) -> Union[FHIRBundle, FHIROperationOutcome]:
        """Convert parsed patient search data to a FHIR Bundle of Patient resources."""
        http_request = kwargs.get('http_request', self.request)
        
        try:
            if parsed_data.get("status") == "error":
                return FHIROperationOutcome.from_error(
                    message=parsed_data.get("message", "Error in parsed patient search data"),
                    code="processing",
                    severity="error"
                )

            # Check if there are patients in response
            if 'patients' in parsed_data and len(parsed_data['patients']) > 0:
                response = FHIRBundle(
                    type="searchset",
                    total=len(parsed_data['patients'])
                )

                for patient_id, patient_name in parsed_data['patients'].items():
                    patient_resource = FHIRPatient(
                        id=patient_id,
                        name=[{
                            "use": "official",
                            "text": patient_name
                        }]
                    )
                    response.append_entry(resource=patient_resource)
                
                return response
            else:
                return FHIROperationOutcome.from_error(
                    message="No patients found for the specified search criteria",
                    code="not-found",
                    severity="information"
                )

        except Exception as e:
            logger.error(f"Error converting patient search data to FHIR FHIRBundle: {e}")
            return FHIROperationOutcome.from_exception(e, code="exception")


class HipoClientServiceRequest(HipoClient):
    """Specialized client for service request related operations in the Hipocrate medical system.

    Handles retrieval and parsing of medical service requests including laboratory
    orders, imaging requests, and other medical service requisitions.
    """

    def __init__(self, service_url: Optional[str] = None, request: Optional[web.Request] = None):
        """Initialize the service request client."""
        super().__init__(service_url=service_url, request=request)
        self.request_url = "/Analyse/LabRequest/buletinRecoltari.asp?id={id}"

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        """Parse a Hipocrate service request page into HipoData."""
        data = HipoData(status="success", message="")

        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            data.store("patient.name", extract_text_after_label(soup, r'Nume Pacient:'))

            patient_ids = extract_ids_from_links(soup, r'../Pacient/edit\.asp\?id=(\d+)')
            if patient_ids:
                data.store("patient.id", patient_ids[0] if isinstance(patient_ids, list) else patient_ids)

            data.store("checkin.medic", extract_text_after_label(soup, r'Medicul:', stop_at=r'-'))

            # Extract admission ID from the "Back" link
            data.store("checkin.id", extract_ids_from_links(soup, r'/checkin\.asp\?id=([^&"]+)'))

            # Extract diagnosis
            data.store("checkin.diagnosis", extract_text_after_label(soup, r'Diagnostic:', 'td'))

            # Extract comments (clinical and lab)
            comment_headers = soup.find_all('td', class_='tdnplus', string=re.compile(r'Comentariile', re.IGNORECASE))
            if len(comment_headers) >= 2:
                # Get the next row which contains the actual comments
                comment_row = comment_headers[0].parent.find_next_sibling('tr')
                if comment_row:
                    comment_tds = comment_row.find_all('td', class_='tdn')
                    if len(comment_tds) >= 2:
                        data.store("request.clinical_comments", comment_tds[0].get_text().strip())
                        data.store("request.lab_comments", comment_tds[1].get_text().strip())

            # Extract imaging studies from the table
            studies_rows = soup.find_all('tr')
            studies = []
            for row in studies_rows:
                cells = row.find_all('td')
                if len(cells) >= 3:
                    # Check if this is a studies row (has numbering in first cell)
                    first_cell_text = cells[0].get_text().strip()
                    if first_cell_text and first_cell_text.isdigit():
                        study_text = cells[1].get_text().strip()
                        if study_text:
                            # Get study type and region
                            study_type, region = identify_study_type_and_region(study_text)
                            studies.append({"id": f"{first_cell_text}",
                                            "title": study_text,
                                            "type": study_type,
                                            "region": region
                            })
            data.store_list("studies", studies)

            # Extract request date_time (Data si ora cererii)
            data.store("request.date_time", extract_text_after_label(soup, r'Data si ora cererii:', stop_at=r'Receptionat'))

            # Extract request urgency
            data.store("request.is_urgent", "~URGENTA~" in html_content)

            return data
        
        except Exception as e:
            logger.error(f"Error parsing service request data: {e}")
            data.set_error(str(e))
            return data

    def fhir_response(self, parsed_data: HipoData, **kwargs) -> Union[FHIRServiceRequest, FHIROperationOutcome]:
        """Convert parsed service request HipoData to a FHIR ServiceRequest resource.

        Transforms parsed service request data into a FHIR-compatible ServiceRequest
        resource with proper structure, references, coding systems, and extensions.

        Args:
            parsed_data: Parsed service request data from parse_data method
            **kwargs: Additional arguments including 'http_request' for host information
                     and 'id' for service request ID

        Returns:
            FHIR ServiceRequest resource or FHIROperationOutcome in case of error
        """
        http_request = kwargs.get('http_request', self.request)
        
        # Get service request ID from the request URL parameters
        service_request_id = kwargs.get('id', '')
        
        try:
            if parsed_data.get("status") == "error":
                return FHIROperationOutcome.from_error(
                    message=parsed_data.get("message", "Error in parsed service request data"),
                    code="processing",
                    severity="error"
                )

            # Create FHIR ServiceRequest resource using the FHIR class
            fhir_service_request = FHIRServiceRequest(
                id=service_request_id,
                status="active",
                intent="order",
                priority="urgent" if parsed_data.get("request.is_urgent", False) else "routine"
            )

            # Create subject reference
            patient_id = parsed_data.get("patient.id")
            subject = FHIRReference(
                reference=f"Patient/{patient_id}"
            )

            # Add patient name to subject if available
            patient_name = parsed_data.get("patient.name")
            if patient_name:
                subject["display"] = patient_name
            fhir_service_request["subject"] = subject

            # Create codeable concept for the service type
            if http_request:
                system_url = f"{http_request.scheme}://{http_request.host}/fhir/CodeSystem/service-types"
            else:
                system_url = "http://example.com/fhir/CodeSystem/service-types"
                
            code = FHIRCodeableConcept(
                coding=[{
                    "system": system_url,
                    "code": "imaging-study",
                    "display": "Imaging Study"
                }],
                text="Imaging Study Request"
            )
            fhir_service_request["code"] = code

            # Add requester if available (requesting doctor)
            medic = parsed_data.get("checkin.medic")
            if medic:
                fhir_service_request["requester"] = FHIRReference(display=medic)

            # Add encounter if we can derive it
            admission_id = parsed_data.get("checkin.id")
            if admission_id:
                # Handle case where admission_id might be a list
                if isinstance(admission_id, list) and len(admission_id) > 0:
                    admission_id = admission_id[0]
                fhir_service_request["encounter"] = FHIRReference(
                    reference=f"Encounter/{admission_id}"
                )

            # Add reason code if diagnosis is available
            diagnosis = parsed_data.get("checkin.diagnosis")
            if diagnosis:
                # Try to extract ICD-10 code from the diagnosis text
                # Format is usually "CODE Description"
                diagnosis_match = re.match(r'^(\d{3,4})\s+(.+)$', diagnosis)
                if diagnosis_match:
                    condition = FHIRReference(
                        reference=f"Condition/{diagnosis_match.group(1)}",
                        display=diagnosis_match.group(2)
                    )
                else:
                    # If no code found, use the entire diagnosis as display text
                    condition = FHIRReference(display=diagnosis)
                fhir_service_request["reason"] = [condition]

            # Add reason reference if clinical comments are available
            clinical_comments = parsed_data.get("request.clinical_comments")
            if clinical_comments:
                fhir_service_request["supportingInfo"] = [{
                    "display": clinical_comments
                }]

            # Add note for lab comments
            lab_comments = parsed_data.get("request.lab_comments")
            if lab_comments:
                fhir_service_request["note"] = [{
                    "text": lab_comments
                }]

            # Add order details for imaging studies
            studies = parsed_data.get("studies")
            if studies:
                order_details = []
                if http_request:
                    study_system_url = f"{http_request.scheme}://{http_request.host}/fhir/CodeSystem/study-codes"
                else:
                    study_system_url = "http://example.com/fhir/CodeSystem/study-codes"
                         
                for study_info in studies:
                    code = study_info.get("id")
                    description = study_info.get("description", "") if isinstance(study_info, dict) else str(study_info)
                    order_detail = FHIRCodeableConcept(
                        coding=[{
                            "system": study_system_url,
                            "code": f"study-{code}",
                            "display": description
                        }],
                        text=description
                    )
                    order_details.append(order_detail)
                fhir_service_request["orderDetail"] = order_details

            # Add authoredOn if request date_time is available
            request_date_time = parsed_data.get("request.date_time")
            if request_date_time:
                # Parse the date_time using our parse_date_time function
                parsed_dt = parse_date_time(request_date_time)
                if parsed_dt:
                    # Convert to ISO format
                    fhir_service_request["authoredOn"] = parsed_dt.isoformat()
                else:
                    fhir_service_request["authoredOn"] = request_date_time

            return fhir_service_request
        except Exception as e:
            logger.error(f"Error converting service request data: {e}")
            return FHIROperationOutcome.from_exception(e, code="exception")


class HipoClientServiceRequestSearch(HipoClientServiceRequest):
    """Specialized client for patient search operations in the Hipocrate medical system.

    Handles searching for patients by various criteria including name, CNP (personal identification number),
    partial CNP, and patient code. Supports both single patient and multiple patient result parsing.
    """

    def __init__(self, service_url: Optional[str] = None, request: Optional[web.Request] = None):
        """Initialize the patient search client."""
        super().__init__(service_url=service_url, request=request)
        self.request_url_all = "/pacient/analyses.asp?type=PA&pacid={pacid}"
        self.request_url_episode = "/Pacient/analysesEpisod.asp?pacid={pacid}"

    async def search(self, patient_id: str, **kwargs) -> HipoData:
        """Search for service requests by patient ID.

        Retrieves all service requests associated with a specific patient.
        If no type is specified, filters by year extracted from the 'dt' parameter.

        Args:
            patient_id: Patient identifier
            **kwargs: Additional arguments (e.g., 'full' for complete data, 
                     'type' for filtering by request type, 'region' for filtering by region,
                     'dt' for filtering by date_time - year will be extracted from this)

        Returns:
            HipoData containing service requests or error information
        """      
        data = HipoData(status="success", message="")

        try:
            if kwargs.get('type'):
                request_url = self.request_url_episode + f"&strDomeniu={ANALYSIS_TYPES[kwargs['type']]['domain']}"
            elif kwargs.get('dt'):
                dt_param = kwargs.get('dt')
                try:
                    if 'T' in dt_param:
                        dt_obj = datetime.fromisoformat(dt_param.replace('Z', '+00:00'))
                    else:
                        dt_obj = datetime.strptime(dt_param, '%Y-%m-%d')
                    year = dt_obj.year
                except (ValueError, TypeError):
                    year = datetime.now().year
                request_url = self.request_url_episode + f"&strAN={year}"
            else:
                request_url = self.request_url_all

            url = request_url.format(pacid=patient_id)
            
            response_text, error_message = await self.get_page(url)

            if error_message:
                data.set_error(error_message)
                return data

            return self.parse_data(response_text, **kwargs)

        except Exception as e:
            data.set_error(f"Data retrieval failed: {str(e)}")
            return data

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        """Parse a Hipocrate service request page into HipoData."""
        data = HipoData(status="success", message="")

        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            if not self.is_expected_page(soup, 'Cereri de Laborator'):
                # Return empty list if not expected page
                data.set_error(f"Unexpected page for ServiceRequestSearch: {self.get_title(soup)}")
                logger.warning(f"{data['message']}: {self.get_error(soup)}")
                return data

            # Extract patient name and ID from the link
            patient_link = soup.find('a', href=re.compile(r'../Pacient/edit\.asp\?id='))
            if patient_link:
                data.store("patient.name", patient_link.get_text())
                data.store("patient.id", extract_id_from_link(patient_link))

            data.store("patient.cnp", extract_text_after_label(soup, r'CNP\s*:', 'tr'))
            if data.get("patient.cnp"):
                parsed_cnp = parse_cnp(data.get("patient.cnp"))
                data.store("patient.gender", parsed_cnp.get("gender"))
                data.store("patient.date", parsed_cnp.get("birth_date"))
                data.store("patient.age", parsed_cnp.get("age"))

            requests = []
            #   function redirect(tip,tipPrintabil,intCodeID, isLabSynevo,barcode)
            #   Example: <a href="#" id="myHref" onclick="redirect('Normal',3,1607394,0,'');return false;">Tipareste buletin recoltari>>></a>
            onclick_links = soup.find_all('a', attrs={'onclick': True})
            
            # Example: <a href="analyseFile.asp?id=1606238" target="_blank">Tipareste buletin rezultate>>></a>
            href_links = soup.find_all('a', href=re.compile(r'analyseFile\.asp\?id=(\d+)'))
            
            # Build a set of IDs already covered by onclick links (O(n) dedup)
            onclick_ids = set()
            for onclick_link in onclick_links:
                m = re.search(r'redirect\([^,]+,[^,]+,(\d+)', onclick_link.get('onclick', ''))
                if m:
                    onclick_ids.add(m.group(1))

            all_links = list(onclick_links)
            for href_link in href_links:
                href_id = extract_id_from_link(href_link, r'analyseFile\.asp\?id=(\d+)')
                if href_id and href_id not in onclick_ids:
                    all_links.append(href_link)
            
            for link in all_links:
                # Extract request ID - either from onclick or href
                request_id = None
                onclick_attr = link.get('onclick', '')
                
                # Check if onclick contains redirect function call
                redirect_match = re.search(r'redirect\([^,]+,[^,]+,(\d+)', onclick_attr)
                if redirect_match:
                    # Extract request ID from intCodeID parameter (3rd parameter in redirect function)
                    request_id = redirect_match.group(1)
                else:
                    # Try to extract from href
                    request_id = extract_id_from_link(link, r'analyseFile\.asp\?id=(\d+)')
                
                if not request_id:
                    continue

                # Keep each request data in HopoData
                request = HipoData(id=request_id, type="unknown", regions=[])

                # Find the parent table row
                parent_row = link.find_parent('tr')
                if not parent_row:
                    # If no parent row, just add the ID without type
                    requests.append(request)
                    continue

                # Get all the cells in row
                cells = parent_row.find_all('td')
                if len(cells) >= 8:
                    # Cell 0: Checkbox (ignore)
                    # Cell 1: Report link (already processed)
                    # Cell 2: Barcode and type
                    cell_2_text = cells[2].get_text(strip=True)
                    try:
                        barcode, exam_type = cell_2_text.split(' - ', 1)
                        type_match = re.search(r'\d{4}-(\w+)', exam_type.strip())
                        if type_match:
                            extracted_type = type_match.group(1).lower()
                            # Check if the extracted type is in our known analysis types
                            if extracted_type in ANALYSIS_TYPES:
                                request.store("type", extracted_type)
                    except ValueError:
                        # Handle case where there's no ' - ' separator
                        # Try to extract type directly from the text
                        type_match = re.search(r'\d{4}-(\w+)', cell_2_text)
                        if type_match:
                            extracted_type = type_match.group(1).lower()
                            if extracted_type in ANALYSIS_TYPES:
                                request.store("type", extracted_type)

                    # Cell 3: Checkin/Checkup code
                    request.store('checkin', extract_ids_from_links(cells[3], r'checkin\.asp\?id=(\d+)'))
                    request.store('checkup', extract_ids_from_links(cells[3], r'checkup\.asp\?cuid=(\d+)'))

                    # Cell 4: Date
                    date_text = cells[4].get_text().strip()
                    if date_text:
                        dt = parse_date_time(date_text)
                        if dt:
                            request.store("date_time", dt.isoformat())
                        else:
                            request.store("date_time", date_text.strip())

                    # Cell 5: Priority
                    request.store("is_urgent", "urgent" in cells[5].get_text().lower())

                    # Cell 6: Analysis type
                    type_text = cells[6].get_text().strip()
                    # Look for pattern like 'XXXX-Radio', 'XXXX-lab', etc.
                    type_match = re.search(r'\d{4}-(\w+)', type_text)
                    if type_match:
                        extracted_type = type_match.group(1).lower()
                        # Check if the extracted type is in our known analysis types
                        if extracted_type in ANALYSIS_TYPES:
                            request.store("type", extracted_type)

                    # Cell 7: Requesting doctor
                    request.store('medic', cells[7].get_text())

                    # Cell 8: barcode
                    request.store('barcode', cells[8].get_text())

                #  Find the next sibling 'tr' to identify the exam types and regions
                try:
                    exams_row = parent_row.find_next_sibling('tr')
                    if exams_row:
                        # Find all cells in this row
                        cells = exams_row.find_all('td')
                        if len(cells) >= 2:
                            exams_text = cells[1].get_text()
                            if exams_text:
                                exams = exams_text.split(';')
                                regions = []
                                for exam in exams:
                                    study_type, region = identify_study_type_and_region(exam)
                                    if region != 'unknown':
                                        regions.append(region)
                                # Store the regions
                                if regions:
                                    request.store_list('regions', regions)
                except Exception as e:
                    logger.warning(f"Error processing exam regions for request {request_id}: {e}")
                    # Continue with empty regions

                # Filter by type
                if kwargs.get('type') and kwargs['type'] != request['type']:
                    continue
                    
                # Filter by region
                if kwargs.get('region') and kwargs['region'] not in request.get('regions', []):
                    continue

                # Append the request data to the requests list
                requests.append(request)

            # Filter requests by date_time
            if kwargs.get('dt'):
                # Parse the date_time string to match against analysis datetimes
                try:
                    # Parse target; strip tzinfo so comparison with naive stored datetimes works
                    target_dt = datetime.fromisoformat(kwargs['dt'].replace('Z', '+00:00')).replace(tzinfo=None)
                    hours_range = 24
                    max_attempts = 10

                    for attempt in range(max_attempts):
                        start_dt = target_dt - timedelta(hours=hours_range)
                        end_dt = target_dt + timedelta(hours=hours_range)

                        filtered_requests = []
                        for req in requests:
                            if "date_time" in req and start_dt <= datetime.fromisoformat(req["date_time"]) <= end_dt:
                                filtered_requests.append(req)

                        if len(filtered_requests) == 1:
                            requests = filtered_requests
                            break
                        elif len(filtered_requests) > 1 and attempt < max_attempts - 1:
                            hours_range = hours_range / 2
                            continue
                        else:
                            requests = filtered_requests
                            break

                except (ValueError, TypeError):
                    data.set_error(f"Invalid date_time format: {kwargs['dt']}")

            # Store the requests
            data.store_list('requests', requests)

        except Exception as e:
            logger.error(f"Error parsing service requests data: {e}")
            data.set_error(str(e))

        # Return the service requests
        return data

    def fhir_bundle_response(self, parsed_data: HipoData, **kwargs) -> Union[FHIRBundle, FHIROperationOutcome]:
        """Convert parsed service request HipoData to a FHIR Bundle of ServiceRequest resources."""
        http_request = kwargs.get('http_request', self.request)
        
        patient_id = kwargs.get('patient_id', '')
        
        try:
            if parsed_data.get("status") == "error":
                return FHIROperationOutcome.from_error(
                    message=parsed_data.get("message", "Error in parsed service request data"),
                    code="processing",
                    severity="error"
                )

            # Check if there are requests in response
            if 'requests' in parsed_data and len(parsed_data['requests']) > 0:
                # Convert multiple requests to FHIR FHIRBundle using the FHIRBundle class
                response = FHIRBundle(
                    type="searchset",
                    total=len(parsed_data['requests'])
                )

                for req in parsed_data['requests']:
                    # Create FHIR ServiceRequest using the FHIR class
                    fhir_service_request = FHIRServiceRequest(
                        id=req["id"],
                        status="active",
                        intent="order",
                        priority="urgent" if req.get("is_urgent") else "routine"
                    )
                    
                    # Add subject reference
                    fhir_service_request["subject"] = FHIRReference(
                        reference=f"Patient/{patient_id}"
                    )
                    
                    # Add code
                    request_type = req["type"]
                    if request_type in ANALYSIS_TYPES:
                        code_display = ANALYSIS_TYPES[request_type]["display"]
                        code_definition = ANALYSIS_TYPES[request_type]["definition"]
                    else:
                        code_display = request_type
                        code_definition = request_type
                    
                    fhir_service_request["code"] = FHIRCodeableConcept(
                        coding=[{
                            "system": f"{http_request.scheme}://{http_request.host}/fhir/CodeSystem/analysis-types" if http_request else "http://example.com/fhir/CodeSystem/analysis-types",
                            "code": request_type,
                            "display": code_display
                        }],
                        text=code_definition
                    )
                    
                    # Add effective date_time if available
                    if req.get("date_time"):
                        fhir_service_request["authoredOn"] = req["date_time"]
                    
                    # Add region information if available
                    if req.get("regions"):
                        fhir_service_request["bodySite"] = []
                        for region in req["regions"]:
                            fhir_service_request["bodySite"].append({
                                "text": region
                            })
                    
                    # Append the entry to the bundle
                    response.append_entry(resource=fhir_service_request)
                
                return response
            else:
                # Create FHIROperationOutcome for no requests found
                return FHIROperationOutcome.from_error(
                    message="No service requests found for the specified patient",
                    code="not-found",
                    severity="information"
                )

        except Exception as e:
            logger.error(f"Error converting service request data to FHIR FHIRBundle: {e}")
            return FHIROperationOutcome.from_exception(e, code="exception")


class HipoClientImagingStudy(HipoClient):
    """Specialized client for imaging study related operations in the Hipocrate medical system.

    Handles retrieval and parsing of medical imaging studies including radiology,
    ultrasound, CT, and MRI examination requests and results.
    """

    def __init__(self, service_url: Optional[str] = None, request: Optional[web.Request] = None):
        """Initialize the service request client."""
        super().__init__(service_url=service_url, request=request)
        self.request_url = "/Analyse/LabRequest/edit.asp?id={id}"

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        """Parse a Hipocrate service request page into HipoData."""
        data = HipoData(status="success", message="")

        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            if not self.is_expected_page(soup, 'Cerere de investigatii paraclinice'):
                # Log snippet of response for debugging
                data.set_error(f"Unexpected page for ImagingStudy: {self.get_title(soup)}")
                logger.warning(f"{data['message']}: {self.get_error(soup)}")
                return data

            # Extract patient name from the table with patient data
            data.store("patient.name", extract_text_after_label(soup, r'Nume:', 'tr', stop_at=r'\['))

            # Extract patient CNP from the table with patient data
            patient_cnp = extract_value_from_input(soup, element_id="strCNP")
            data.store("patient.cnp", patient_cnp)
            if patient_cnp:
                parsed_cnp = parse_cnp(patient_cnp)
                data.store("patient.gender", parsed_cnp.get("gender", ""))
                data.store("patient.birth_date", parsed_cnp.get("birth_date", ""))
                data.store("patient.age", parsed_cnp.get("age", ""))

            # Extract patient code from the table with patient data
            patient_ids = extract_ids_from_links(soup, r'/pacient/edit\.asp\?id=(\d+)')
            if patient_ids:
                data.store("patient.id", patient_ids[0] if isinstance(patient_ids, list) else patient_ids)
            
            # Extract checkin ID
            data.store("checkin.id", extract_ids_from_links(soup, r'/files/checkin\.asp\?id=(\d+)'))

            # Extract barcode
            data.store("request.barcode", extract_text_after_label(soup, r'Cerere de investigatii (?!paraclinice)'))

            data.store("checkin.medic", extract_text_after_label(soup, r'Medic:', 'tr'))

            # Extract the clinical comments
            data.store("checkin.diagnosis", extract_text_after_label(soup, r'prezumtiv:', 'tr'))

            # Extract the clinical comments
            data.store("request.clinical_comments", extract_text_after_label(soup, r'Informatii suplimentare:', 'tr', stop_at=r'Motiv'))

            # Extract the lab comments
            data.store("request.lab_comments", extract_text_from_element(soup, element_id="strComments"))

            # Extract the justification
            data.store("request.justification", extract_text_from_element(soup, element_id="strJustificare"))

            data.store("request.icd10", extract_text_after_label(soup, r'Diagnostic:', 'tr'))

            req = extract_text_after_label(soup, r'Ceruta:', 'tr')
            if req and '-' in req:
                try:
                    request_medic, request_date_time = req.split('-', 1)
                    data.store("request.medic", request_medic)
                    dt = parse_date_time(request_date_time)
                    if dt:
                        data.store("request.date_time", dt.isoformat())
                    else:
                        data.store("request.date_time", request_date_time.strip())
                except ValueError:
                    data.store("request.info", req)

            validator = extract_text_after_label(soup, r'Validat de:', 'td', stop_at=r'Data')
            if validator:
                data.store("validation.validator", validator)

            validation_datetime = extract_value_from_input(soup, element_id="dataefectuarii")
            if validation_datetime:
                dt = parse_date_time(validation_datetime)
                if dt:
                    data.store("validation.date_time", dt.isoformat())
                else:
                    data.store("validation.date_time", validation_datetime)
            
            # For each strAnalyseExec input, find the parent 'td' and extract examination name from first 'b' element
            studies = []
            for input_elem in soup.find_all('input', {'name': 'strAnalyseExec'}):
                try:
                    study_title = ""
                    study_result = None
                    
                    parent_td = input_elem.find_parent('td')
                    if parent_td:
                        first_b = parent_td.find('b')
                        if first_b:
                            study_title = first_b.get_text(strip=True)
                        else:
                            study_title = parent_td.get_text(strip=True)
                            
                    # Find the 'table' parent and then the 'center' sibling
                    if parent_td:
                        parent_table = parent_td.find_parent('table')
                        if parent_table:
                            container = parent_table.find_next_sibling('center')
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
                                                study_result = html_to_markdown(str(subelements[0]))
                                            else:
                                                # Otherwise, process the entire div
                                                study_result = html_to_markdown(str(cells[1]))
                    
                    # Append the study if the data is valid
                    if study_title and study_result:
                        # Get study type and region
                        study_type, region = identify_study_type_and_region(study_title)
                        study = {
                            "title": study_title,
                            "result": study_result,
                            "type": study_type,
                            "region": region
                        }
                        studies.append(study)
                except Exception as e:
                    logger.warning(f"Error processing study for input element: {e}")
                    # Continue processing other studies
            data.store_list("studies", studies)

            # Store urgency flag
            data.store("request.is_urgent", "~URGENTA~" in html_content)

            return data

        except Exception as e:
            logger.error(f"Error parsing report data: {e}")
            return HipoData(status="error", message=str(e))

    def fhir_response(self, parsed_data: HipoData, **kwargs) -> Union[FHIRImagingStudy, FHIROperationOutcome]:
        """Convert parsed imaging study HipoData to a FHIR ImagingStudy resource."""
        http_request = kwargs.get('http_request', self.request)
        
        study_id = kwargs.get('id', '')
        
        try:
            if parsed_data.get("status") == "error":
                return FHIROperationOutcome.from_error(
                    message=parsed_data.get("message", "Error in parsed imaging study data"),
                    code="processing",
                    severity="error"
                )

            # Create FHIR ImagingStudy resource using the FHIR class
            fhir_imaging_study = FHIRImagingStudy(
                id=study_id,
                status="available",
                subject={
                    "reference": f"Patient/{parsed_data.get('patient.id', '')}"
                }
            )

            # Add basedOn reference if available
            if study_id:
                fhir_imaging_study["basedOn"] = [{
                    "reference": f"ServiceRequest/{study_id}"
                }]

            # Add started date_time if available
            request_date_time = parsed_data.get("request.date_time")
            if request_date_time:
                fhir_imaging_study["started"] = request_date_time

            # Add modality if available in studies
            studies = parsed_data.get("studies", [])
            if studies and isinstance(studies[0], dict):
                mod_code, mod_display = DICOM_MODALITY.get(
                    studies[0].get("type", "").lower(), DICOM_MODALITY["other"]
                )
                fhir_imaging_study["modality"] = [{
                    "system": "http://dicom.nema.org/resources/ontology/DCM",
                    "code": mod_code,
                    "display": mod_display
                }]

            identifiers = []
            if parsed_data.get("patient.name"):
                identifiers.append({
                    "system": f"{http_request.scheme}://{http_request.host}/fhir/NamingSystem/patient-name" if http_request else "http://example.com/fhir/NamingSystem/patient-name",
                    "value": parsed_data.get("patient.name")
                })

            if parsed_data.get("patient.cnp"):
                identifiers.append({
                    "system": f"{http_request.scheme}://{http_request.host}/fhir/NamingSystem/patient-cnp" if http_request else "http://example.com/fhir/NamingSystem/patient-cnp",
                    "value": parsed_data.get("patient.cnp")
                })

            if identifiers:
                fhir_imaging_study["identifier"] = identifiers

            # Add description from first study
            if studies and len(studies) > 0 and isinstance(studies[0], dict):
                fhir_imaging_study["description"] = studies[0].get("title", "Imaging Study")

            # Add performer if available
            if parsed_data.get("checkin.medic"):
                fhir_imaging_study["performer"] = [
                    {
                        "actor": {
                            "display": parsed_data.get("checkin.medic")
                        }
                    }
                ]

            # Add referrer if requesting medic is available
            if parsed_data.get("request.medic"):
                fhir_imaging_study["referrer"] = {
                    "display": parsed_data.get("request.medic")
                }

            # Add series for each study
            series_list = []
            if studies:
                for i, study in enumerate(studies):
                    if not isinstance(study, dict):
                        continue
                        
                    series = {
                        "uid": f"urn:oid:1.2.840.99999999.1.{study_id}.{i+1}",
                        "number": i+1,
                        "modality": {
                            "system": "http://dicom.nema.org/resources/ontology/DCM",
                            "code": "OT",  # Other
                            "display": "Other"
                        },
                        "description": study.get("title", "Imaging Study")
                    }
                    
                    # Add started date_time if available
                    if request_date_time:
                        series["started"] = request_date_time
                    
                    # Use the study modality for the series if available
                    s_code, s_display = DICOM_MODALITY.get(
                        study.get("type", "").lower(), DICOM_MODALITY["other"]
                    )
                    series["modality"] = {
                        "system": "http://dicom.nema.org/resources/ontology/DCM",
                        "code": s_code,
                        "display": s_display
                    }
                        
                    series_list.append(series)

            if series_list:
                fhir_imaging_study["series"] = series_list

            # Add reason for study if diagnosis is available
            if parsed_data.get("checkin.diagnosis"):
                fhir_imaging_study["reason"] = [
                    {
                        "text": parsed_data.get("checkin.diagnosis")
                    }
                ]

            # Add note if clinical comments are available
            if parsed_data.get("request.clinical_comments"):
                fhir_imaging_study["note"] = [
                    {
                        "text": parsed_data.get("request.clinical_comments")
                    }
                ]

            return fhir_imaging_study

        except Exception as e:
            logger.error(f"Error converting imaging study data to FHIR: {e}")
            return FHIROperationOutcome.from_exception(e, code="exception")


class HipoClientDiagnosticReport(HipoClient):
    """Specialized client for diagnostic report related operations in the Hipocrate medical system.

    Handles retrieval and parsing of diagnostic reports including laboratory results,
    imaging study reports, and other diagnostic examination results.
    """

    def __init__(self, service_url: Optional[str] = None, request: Optional[web.Request] = None):
        """Initialize the service request client."""
        super().__init__(service_url=service_url, request=request)
        self.request_url = "/analyse/Reports/analyseFile.asp?id={id}"

    async def fetch_and_parse(self, *args, **kwargs):
        """Fetch and parse a diagnostic report, evicting the cache if no study results found.

        An empty studies list means the report has not been filled yet in Hipocrate.
        Caching that response would prevent the next request from picking up the real data,
        so we evict the URL from cache when studies is empty.
        """
        parsed_data = await super().fetch_and_parse(*args, **kwargs)
        if parsed_data.get("status") != "error":
            studies = parsed_data.get("studies") or []
            all_empty = all(not s.get("result") for s in studies) if studies else True
            if all_empty:
                url = self.request_url.format(**kwargs)
                self.cache_remove(self.get_full_url(url))
                logger.debug(f"Evicted empty diagnostic report from cache: {url}")
        return parsed_data

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        """Parse a Hipocrate service request page into HipoData."""
        data = HipoData(status="success", message="")

        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            if not self.is_expected_page(soup, 'Buletin de investigatii paraclinice'):
                # Log snippet of response for debugging
                data.set_error(f"Unexpected page for DiagnosticReport: {self.get_title(soup)}")
                logger.warning(f"{data['message']}: {self.get_error(soup)}")
                return data

            # Extract patient name from the table with patient data
            data.store("patient.name", extract_text_after_label(soup, r'PACIENT:', 'td', stop_at=r'Varsta'))

            # Extract barcode
            data.store("request.barcode", extract_text_after_label(soup, r'Nr.: '))

            data.store("checkin.medic", extract_text_after_label(soup, r'Solicitat de:', 'td'))

            # Extract the clinical comments
            data.store("checkin.diagnosis", extract_text_after_label(soup, r'DIAGNOSTIC DE TRIMITERE:', 'td'))

            data.store("request.medic", extract_text_after_label(soup, r'TRIMIS DE:\s*MEDIC', 'tr', stop_at=r'SECTIA'))

            # Extract the clinical comments
            data.store("request.clinical_comments", extract_text_after_label(soup, r'DG\.PREZUMTIV:', 'td'))

            # Extract the lab comments
            data.store("request.lab_comments", extract_text_after_label(soup, r'INDICATII SPECIALE:', 'td'))

            # Extract performer (Efectuata de catre:)
            data.store("study.performer", extract_text_after_label(soup, r'Efectuata de catre:'))

            data.store("study.medic", extract_text_after_label(soup, r'MEDIC,|Medic validator:', 'td', stop_at=r'Semnatura'))

            # Extract study date_time
            study_datetime = extract_text_after_label(soup, r'Data investigatiei:', stop_at=r'Efectuata')
            if study_datetime:
                dt = parse_date_time(study_datetime)
                if dt:
                    data.store("study.date_time", dt.isoformat())
                else:
                    data.store("study.date_time", study_datetime)

            # Extract multiple reports: find all elements with text starting with "REZULTAT:"
            studies = []
            for result_element in soup.find_all(string=re.compile(r'^REZULTAT:', re.IGNORECASE)):
                try:
                    # The investigation name is the text after "REZULTAT:" in the element
                    element_text = result_element.get_text() if hasattr(result_element, 'get_text') else str(result_element)
                    investigation_match = re.search(r'REZULTAT:\s*(.*?)(?:\s*$)', element_text, re.IGNORECASE)
                    study_title = ""
                    if investigation_match:
                        study_title = investigation_match.group(1).strip()

                    # Find the next div sibling which contains the actual result
                    study_result = ""
                    if hasattr(result_element, 'find_next'):
                        result_div = result_element.find_next('div')
                        if result_div:
                            # Check if the div contains only a single <b> tag as its child
                            div_children = list(result_div.children)
                            # Filter out text nodes that contain only whitespace
                            element_children = [child for child in div_children if hasattr(child, 'name') and child.name]
                            if len(element_children) == 1 and element_children[0].name == 'b':
                                # If the only child is a <b> tag, use its content directly
                                study_result = html_to_markdown(str(element_children[0]))
                            else:
                                # Otherwise, process the entire div
                                study_result = html_to_markdown(str(result_div))

                    # Add to reports list if we have valid data
                    if study_title or study_result:
                        # Process investigation name to identify study type and region
                        study_type, region = identify_study_type_and_region(study_title)
                        study = {
                                "title": study_title,
                                "result": study_result,
                                "type": study_type,
                                "region": region
                            }
                        studies.append(study)
                except Exception as e:
                    logger.error(f"Error parsing individual report: {e}")
                    continue
            data.store_list("studies", studies)


            # Store urgency flag
            data.store("request.is_urgent", "~URGENTA~" in html_content)

            return data

        except Exception as e:
            logger.error(f"Error parsing report data: {e}")
            return HipoData(status="error", message=str(e))

    def fhir_response(self, parsed_data: HipoData, **kwargs) -> Union[FHIRDiagnosticReport, FHIROperationOutcome]:
        """Convert parsed diagnostic report HipoData to a FHIR DiagnosticReport resource."""
        http_request = kwargs.get('http_request', self.request)
        
        report_id = kwargs.get('id', '')
        
        try:
            if parsed_data.get("status") == "error":
                return FHIROperationOutcome.from_error(
                    message=parsed_data.get("message", "Error in parsed diagnostic report data"),
                    code="processing",
                    severity="error"
                )

            # Create FHIR DiagnosticReport resource using the FHIR class
            fhir_report = FHIRDiagnosticReport(
                id=report_id,
                status="final",
                code={
                    "coding": [
                        {
                            "system": f"{http_request.scheme}://{http_request.host}/fhir/CodeSystem/report-types" if http_request else "http://example.com/fhir/CodeSystem/report-types",
                            "code": "imaging-report",
                            "display": "Imaging Report"
                        }
                    ],
                    "text": "Diagnostic Report"
                },
                subject={
                    "reference": f"Patient/{parsed_data.get('patient.id', '')}"
                }
            )

            # Add basedOn reference to ServiceRequest if available
            if report_id:
                fhir_report["basedOn"] = [{
                    "reference": f"ServiceRequest/{report_id}"
                }]

            # Add effective date if available
            study_datetime = parsed_data.get("study.date_time")
            if study_datetime:
                fhir_report["effectiveDateTime"] = study_datetime
            else:
                request_date_time = parsed_data.get("request.date_time")
                if request_date_time:
                    fhir_report["effectiveDateTime"] = request_date_time
                else:
                    # Try to get date_time from checkin if available
                    checkin_datetime = parsed_data.get("checkin.date_time")
                    if checkin_datetime:
                        fhir_report["effectiveDateTime"] = checkin_datetime

            # Add performer if available
            performer = parsed_data.get("study.performer")
            if performer:
                fhir_report["performer"] = [
                    {
                        "display": performer
                    }
                ]

            # Add results interpreter
            medic = parsed_data.get("study.medic")
            if medic:
                fhir_report["resultsInterpreter"] = [
                    {
                        "display": medic
                    }
                ]

            # Add results if studies are available
            studies = parsed_data.get("studies")
            if studies:
                fhir_report["result"] = [
                    {
                        "reference": f"Observation/{report_id}"
                    }
                ]

                # Add presentedForm with study results
                fhir_report["presentedForm"] = []
                for study in studies:
                    if isinstance(study, dict) and study.get("result"):
                        fhir_report["presentedForm"].append(
                            {
                                "contentType": "text/markdown",
                                "title": study.get("title", ""),
                                "data": study["result"],
                                "type": study.get("type", ""),
                                "region": study.get("region", "")
                            }
                        )

            # Add extensions for additional data
            extensions = []

            # Add requester information
            requester = parsed_data.get("request.medic")
            if requester:
                extensions.append({
                    "url": f"{http_request.scheme}://{http_request.host}/fhir/StructureDefinition/diagnostic-report-requester" if http_request else "http://example.com/fhir/StructureDefinition/diagnostic-report-requester",
                    "valueString": requester
                })

            # Add admission ID if available
            admission_id = parsed_data.get("checkin.id")
            if admission_id:
                extensions.append({
                    "url": f"{http_request.scheme}://{http_request.host}/fhir/StructureDefinition/diagnostic-report-encounter" if http_request else "http://example.com/fhir/StructureDefinition/diagnostic-report-encounter",
                    "valueString": admission_id if not isinstance(admission_id, list) else admission_id[0] if len(admission_id) > 0 else ""
                })

            # Add barcode if available
            barcode = parsed_data.get("request.barcode")
            if barcode:
                extensions.append({
                    "url": f"{http_request.scheme}://{http_request.host}/fhir/StructureDefinition/diagnostic-report-barcode" if http_request else "http://example.com/fhir/StructureDefinition/diagnostic-report-barcode",
                    "valueString": barcode
                })

            # Add diagnosis if available
            diagnosis = parsed_data.get("checkin.diagnosis")
            if diagnosis:
                extensions.append({
                    "url": f"{http_request.scheme}://{http_request.host}/fhir/StructureDefinition/diagnostic-report-diagnosis" if http_request else "http://example.com/fhir/StructureDefinition/diagnostic-report-diagnosis",
                    "valueString": diagnosis
                })

            # Add ICD10 code if available
            icd10 = parsed_data.get("request.icd10")
            if icd10:
                extensions.append({
                    "url": f"{http_request.scheme}://{http_request.host}/fhir/StructureDefinition/diagnostic-report-icd10" if http_request else "http://example.com/fhir/StructureDefinition/diagnostic-report-icd10",
                    "valueString": icd10
                })

            # Add lab comments if available
            lab_comments = parsed_data.get("request.lab_comments")
            if lab_comments:
                extensions.append({
                    "url": f"{http_request.scheme}://{http_request.host}/fhir/StructureDefinition/diagnostic-report-lab-comments" if http_request else "http://example.com/fhir/StructureDefinition/diagnostic-report-lab-comments",
                    "valueString": lab_comments
                })

            # Add justification if available
            justification = parsed_data.get("request.justification")
            if justification:
                extensions.append({
                    "url": f"{http_request.scheme}://{http_request.host}/fhir/StructureDefinition/diagnostic-report-justification" if http_request else "http://example.com/fhir/StructureDefinition/diagnostic-report-justification",
                    "valueString": justification
                })

            if extensions:
                fhir_report["extension"] = extensions

            identifiers = []

            # Add barcode as identifier if available
            if barcode:
                identifiers.append({
                    "system": f"{http_request.scheme}://{http_request.host}/fhir/NamingSystem/barcode" if http_request else "http://example.com/fhir/NamingSystem/barcode",
                    "value": barcode
                })

            if identifiers:
                fhir_report["identifier"] = identifiers

            return fhir_report

        except Exception as e:
            logger.error(f"Error converting diagnostic report data to FHIR: {e}")
            return FHIROperationOutcome.from_exception(e, code="exception")


class HipoClientCheckout(HipoClient):
    """Specialized client for checkout-related operations in the Hipocrate medical system.

    Handles retrieval and parsing of patient discharge/checkout information from
    the Hipocrate system, including admission details, discharge summaries,
    diagnoses, and medic information.
    """

    def __init__(self, service_url: Optional[str] = None, request: Optional[web.Request] = None):
        """Initialize the checkout client."""
        super().__init__(service_url=service_url, request=request)
        self.request_url = "/files/checkout.asp?id={id}"

    async def fetch_and_parse(self, *args, **kwargs):
        """Fetch and parse a checkout, evicting cache if epicrisis is empty.

        An empty epicrisis means the discharge summary has not been written yet.
        Evict so the next request can pick up the filled-in text.
        """
        parsed_data = await super().fetch_and_parse(*args, **kwargs)
        if parsed_data.get("status") != "error":
            if not parsed_data.get("checkout.epicrisis"):
                url = self.request_url.format(**kwargs)
                self.cache_remove(self.get_full_url(url))
                logger.debug(f"Evicted empty checkout epicrisis from cache: {url}")
        return parsed_data

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        """Parse a Hipocrate checkout/discharge page into HipoData."""
        data = HipoData(status="success", message="")

        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            if not self.is_expected_page(soup, 'FISA EXTERNARE'):
                data.set_error("Page is not a discharge page")
                logger.warning("Page is not a discharge page")
                return data

            # Extract patient name and ID from the link
            patient_link = soup.find('a', href=re.compile(r'../Pacient/edit\.asp\?id='))
            if patient_link:
                data.store("patient.name", patient_link.get_text())
                data.store("patient.id", extract_id_from_link(patient_link))

            data.store("patient.cnp", extract_text_after_label(soup, r'CNP\s*:', 'tr'))
            if data.get("patient.cnp"):
                parsed_cnp = parse_cnp(data.get("patient.cnp"))
                data.store("patient.gender", parsed_cnp.get("gender"))
                data.store("patient.date", parsed_cnp.get("birth_date"))
                data.store("patient.age", parsed_cnp.get("age"))


            # Extract presentation ID
            presentation_ids = extract_ids_from_links(soup, r'presentation\.asp\?id=(\d+)')
            if presentation_ids:
                data.store("presentation.id", presentation_ids)


            # Extract admission ID
            checkin_ids = extract_ids_from_links(soup, r'checkin\.asp\?id=(\d+)')
            if checkin_ids:
                data.store("checkin.id", checkin_ids)

            data.store("checkin.medic", extract_text_after_label(soup, r'Medic\s*:', 'tr'))

            # Extract ward
            data.store("checkin.ward", extract_text_after_label(soup, r'Sectie\s*:', 'tr'))

            # Extract checkin diagnostic
            data.store("checkin.diagnosis", extract_text_after_label(soup, r'Diagnostic\s*:', 'tr'))

            # Extract checkin date and time from input fields
            data.store("checkin.date", extract_value_from_input(soup, element_id='sCIDate'))
            data.store("checkin.time", extract_value_from_input(soup, element_id='sCITime'))
            
            # Create combined checkin date_time
            checkin_date = data.get("checkin.date")
            checkin_time = data.get("checkin.time")
            if checkin_date and checkin_time:
                data.store("checkin.date_time", f'{checkin_date} {checkin_time}')


            # Extract checkout date and time from input fields
            data.store("checkout.date", extract_value_from_input(soup, element_id='sCODate'))
            data.store("checkout.time", extract_value_from_input(soup, element_id='sCOTime'))
            
            # Create combined checkout date_time
            checkout_date = data.get("checkout.date")
            checkout_time = data.get("checkout.time")
            if checkout_date and checkout_time:
                data.store("checkout.date_time", f'{checkout_date} {checkout_time}')

            # Extract epicrisis (textarea with id "sEpicrisysHtmlArea")
            data.store("checkout.epicrisis", extract_text_from_element(soup, 'sEpicrisys'))

            # Extract diagnostic (textarea after 'Diagnostic externare')
            data.store("checkout.diagnosis", extract_textarea_after_label(soup, r'Diagnostic externare[^:]*:'))

            data.store("checkout.medic", extract_selected_from_dropdown(soup, name='iCOMedicID'))

            # Extract ward
            data.store("checkout.ward", extract_selected_from_dropdown(soup, name='sSectionCode'))

            # Extract surgery (textarea with id "sBOProtocolHtmlArea")
            data.store("checkout.surgery", extract_text_from_element(soup, 'sBOProtocol'))

            # Extract recommendations (textarea with id 'sRecommendationsHtmlArea')
            data.store("checkout.recommendations", extract_text_from_element(soup, 'sRecommendations'))

            # Extract ICD10 diagnostic from textarea with name "sCODiagnosis"
            data.store("checkout.icd10", extract_text_from_element(soup, name='sCODiagnosis'))

            # Add the id, if provided
            if 'id' in kwargs:
                data.store("checkout.id", kwargs["id"])

            return data

        except Exception as e:
            logger.error(f"Error parsing checkout data: {e}")
            data.set_error(str(e))
            return data

    def fhir_response(self, parsed_data: HipoData, **kwargs) -> Union[FHIREncounter, FHIROperationOutcome]:
        """Convert parsed checkout HipoData to a FHIR Encounter resource.
        """
        try:
            if parsed_data.get("status") == "error":
                return FHIROperationOutcome.from_error(
                    message=parsed_data.get("message", "Error in parsed checkout data"),
                    code="processing",
                    severity="error"
                )

            encounter_id = parsed_data.get('checkout.id', '')
            fhir_encounter = FHIREncounter(
                id=encounter_id,
                status="discharged",
                type=[
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
                subject={
                    "reference": f"Patient/{parsed_data.get('patient.id', '')}"
                }
            )
            
            # Add performer if available (from checkout medic)
            checkout_medic = parsed_data.get("checkout.medic")
            if checkout_medic:
                fhir_encounter["participant"] = [{
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
                        "display": checkout_medic
                    }
                }]

            # Add reason (admission diagnostic) if available
            admission_diagnosis = parsed_data.get("checkin.diagnosis")
            if admission_diagnosis:
                fhir_encounter["reasonCode"] = [
                    {
                        "text": admission_diagnosis
                    }
                ]

            # Add text summary if epicrisis exists
            epicrisis = parsed_data.get("checkout.epicrisis")
            if epicrisis:
                # Also add as a note
                fhir_encounter["note"] = [
                    {
                        "text": epicrisis
                    }
                ]

            # Add diagnosis if available
            if admission_diagnosis:
                fhir_encounter["diagnosis"] = [
                    {
                        "condition": {
                            "reference": f"Condition/admission-{encounter_id}",
                            "display": admission_diagnosis
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
            discharge_diagnosis = parsed_data.get("checkout.diagnosis")
            if discharge_diagnosis:
                if "diagnosis" not in fhir_encounter:
                    fhir_encounter["diagnosis"] = []
                fhir_encounter["diagnosis"].append(
                    {
                        "condition": {
                            "reference": f"Condition/discharge-{encounter_id}",
                            "display": discharge_diagnosis
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

            # Add period for admission and discharge times
            checkin_datetime = parsed_data.get("checkin.date_time")
            checkout_datetime = parsed_data.get("checkout.date_time")
            if checkin_datetime or checkout_datetime:
                period = {}
                if checkin_datetime:
                    dt = parse_date_time(checkin_datetime)
                    period["start"] = dt.isoformat() if dt else checkin_datetime
                if checkout_datetime:
                    dt = parse_date_time(checkout_datetime)
                    period["end"] = dt.isoformat() if dt else checkout_datetime
                fhir_encounter["period"] = period

            # Add location/ward information
            checkin_ward = parsed_data.get("checkin.ward")
            checkout_ward = parsed_data.get("checkout.ward")
            if checkin_ward or checkout_ward:
                location = []
                if checkin_ward:
                    location.append({
                        "location": {
                            "display": checkin_ward
                        },
                        "status": "active"
                    })
                if checkout_ward and checkout_ward != checkin_ward:
                    location.append({
                        "location": {
                            "display": checkout_ward
                        },
                        "status": "completed"
                    })
                if location:
                    fhir_encounter["location"] = location

            return fhir_encounter
        except Exception as e:
            logger.error(f"Error converting checkout data to FHIR: {e}")
            return FHIROperationOutcome.from_exception(e, code="exception")
