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

    async def close_user_session(self, username: str) -> None:
        """Close one user's session and forget its authentication state."""
        session = self.user_sessions.pop(username, None)
        if session and not session.closed:
            logger.info(f"Closing session for user {username}")
            await session.close()
        self._authenticated.pop(username, None)

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
            city = extract_selected_from_dropdown(soup, element_id='strDomLegal_LocId')
            street = extract_value_from_input(soup, element_id='strDomLegal_strada')
            address_parts = [p for p in [street, city] if p]
            data.store("patient.address", ", ".join(address_parts) if address_parts else None)

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
                # Not a CNP length — treat as a direct patient ID and fetch the patient
                # page immediately instead of going through the search form (the form
                # does not accept raw numeric IDs of this length and returns an
                # unrecognised page).  Temporarily swap request_url so the inherited
                # fetch_and_parse uses the patient-detail URL, then restore it.
                logger.info(f"Performing direct patient ID lookup for: {search_term}")
                saved_url = self.request_url
                self.request_url = "/Pacient/edit.asp?id={id}"
                try:
                    return await self.fetch_and_parse(id=search_term)
                finally:
                    self.request_url = saved_url
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

            pattern = r"\.\./Pacient/edit\.asp\?id=(\d+)"
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
        self.request_url = "/PARA/Printabile/buletinRecoltari.asp?id={id}"

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        """Parse a Hipocrate service request page into HipoData."""
        data = HipoData(status="success", message="")

        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            data.store("patient.name", extract_text_after_label(soup, r'NUME PACIENT:'))
            data.store("checkin.medic", extract_text_after_label(soup, r'MEDICUL:'))
            data.store("request.date_time", extract_text_after_label(soup, r'DATA SI ORA CERERII:', stop_at=r'RECEPTIONAT'))
            data.store("request.barcode", soup.find('div', class_='div_barCode').get_text(strip=True) if soup.find('div', class_='div_barCode') else None)
            data.store("request.is_urgent", bool(soup.find('p', class_='pUrgenta')))

            # Studies: numbered rows in table (index in first cell)
            studies = []
            seen_titles = set()
            for row in soup.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) >= 3:
                    first = cells[0].get_text().strip()
                    if first and first.isdigit():
                        study_text = cells[1].get_text().strip()
                        if study_text and study_text not in seen_titles:
                            seen_titles.add(study_text)
                            study_type, region = identify_study_type_and_region(study_text)
                            studies.append({"id": first, "title": study_text, "type": study_type, "region": region})
            data.store_list("studies", studies)

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
        self.request_url_all = "/Pacient/analysesALL.asp?type=PA&pacid={pacid}"
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
                request_url = self.request_url_episode + f"&strDomeniu={ANALYSIS_TYPES[kwargs['type']]['domain']}&NrPePag=100"
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
                request_url = self.request_url_episode + f"&strAN={year}&NrPePag=100"
            else:
                # Fetch all imaging domains in parallel and merge
                imaging_types = [t for t, v in ANALYSIS_TYPES.items() if v['domain'] != 0]
                tasks = []
                for t in imaging_types:
                    url = (self.request_url_episode + f"&strDomeniu={ANALYSIS_TYPES[t]['domain']}&NrPePag=100").format(pacid=patient_id)
                    tasks.append(self.get_page(url))
                results = await asyncio.gather(*tasks)
                merged = HipoData(status="success", message="")
                seen_ids = set()
                all_requests = []
                for html, err in results:
                    if err or not html:
                        continue
                    parsed = self.parse_data(html)
                    if parsed.get('patient') and not merged.get('patient'):
                        merged['patient'] = parsed['patient']
                    for req in parsed.get('requests', []):
                        if req['id'] not in seen_ids:
                            seen_ids.add(req['id'])
                            all_requests.append(req)
                all_requests.sort(key=lambda r: r.get('date_time', ''), reverse=True)
                merged['requests'] = all_requests
                return merged

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
            seen_ids = set()
            all_rows = soup.find_all('tr')
            for row_idx, row in enumerate(all_rows):
                cells = row.find_all('td')
                if len(cells) != 8:
                    continue

                # Cell 0 contains buletinRecoltari link (request ID)
                recoltari_link = cells[0].find('a', href=re.compile(r'buletinRecoltari\.asp\?id=(\d+)'))
                if not recoltari_link:
                    continue
                request_id = re.search(r'buletinRecoltari\.asp\?id=(\d+)', recoltari_link['href'])
                if not request_id:
                    continue
                request_id = request_id.group(1)
                if request_id in seen_ids:
                    continue
                seen_ids.add(request_id)

                request = HipoData(id=request_id, type="unknown", regions=[])

                # Cell 1: "BARCODE - NNNN-type"
                cell1_text = cells[1].get_text(strip=True)
                type_match = re.search(r'\d{4}-(\w+)', cell1_text)
                if type_match:
                    extracted_type = type_match.group(1).lower()
                    if extracted_type in ANALYSIS_TYPES:
                        request.store("type", extracted_type)
                request.store("barcode", cell1_text.split(' - ')[0] if ' - ' in cell1_text else cell1_text)

                # Cell 2: checkup link
                request.store('checkup', extract_ids_from_links(cells[2], r'checkup\.asp\?cuid=(\d+)'))

                # Cell 3: date
                date_text = cells[3].get_text(strip=True)
                if date_text:
                    dt = parse_date_time(date_text)
                    if dt:
                        request.store("date_time", dt.isoformat())
                    else:
                        request.store("date_time", date_text)

                # Cell 4: priority
                request.store("is_urgent", "urgent" in cells[4].get_text().lower())

                # Cell 5: section code
                request.store("section", cells[5].get_text(strip=True))

                # Cell 6: doctor
                request.store("medic", cells[6].get_text(strip=True))

                # Check for BuletinAnalize link (results available)
                analize_link = cells[0].find('a', href=re.compile(r'BuletinAnalize\.asp\?id=\d+&type=1'))
                if analize_link:
                    result_id = re.search(r'BuletinAnalize\.asp\?id=(\d+)', analize_link['href'])
                    if result_id:
                        request.store("result_id", result_id.group(1))

                # Next 2-cell sibling row contains exam description
                try:
                    next_row = all_rows[row_idx + 1] if row_idx + 1 < len(all_rows) else None
                    if next_row:
                        next_cells = next_row.find_all('td')
                        if len(next_cells) == 2:
                            exams_text = next_cells[1].get_text(strip=True)
                            if exams_text:
                                regions = []
                                for exam in exams_text.split(';'):
                                    _, region = identify_study_type_and_region(exam)
                                    if region != 'unknown':
                                        regions.append(region)
                                if regions:
                                    request.store_list('regions', regions)
                except Exception as e:
                    logger.warning(f"Error processing exam regions for request {request_id}: {e}")

                # Filter by type
                if kwargs.get('type') and kwargs['type'] != request.get('type'):
                    continue

                # Filter by region
                if kwargs.get('region') and kwargs['region'] not in request.get('regions', []):
                    continue

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

                    # Add ordering physician
                    if req.get("medic"):
                        fhir_service_request["requester"] = FHIRReference(display=req["medic"])

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


def _parse_buletin_header(soup, data: HipoData) -> None:
    """Parse the shared header of BuletinAnalize pages (type=1 and type=2).

    Row 1 cell 1: "BULETIN ... Data si ora recoltarii: <date>"
    Row 1 cell 2: "Nr.Reg.<id>Cod cerere:<barcode>..."
    Row 2 cell 0: "NUME:<name>CNP:<cnp>..."
    Row 2 cell 1: "...COD PACIENT:<id>Urgenta:<urgency>SEX:<sex>"
    Row 2 cell 2: "SECTIE:<section>MEDIC:<medic>"
    """
    rows = soup.find_all('tr')
    if len(rows) < 3:
        return

    def extract_field(text, label, stop_labels=None):
        pattern = re.escape(label)
        m = re.search(pattern + r'(.*?)(?=' + '|'.join(re.escape(s) for s in (stop_labels or [])) + r'|$)', text, re.DOTALL)
        return m.group(1).strip() if m else None

    try:
        row1_cells = rows[1].find_all('td') if len(rows) > 1 else []
        row2_cells = rows[2].find_all('td') if len(rows) > 2 else []

        # Extract date and barcode from page header
        page_text = soup.get_text(' ')
        header_html = str(soup)
        date_m = re.search(r'Data si ora recoltarii setului de analize:\s*(.*?)(?:Data si ora|$)', page_text)
        if date_m:
            dt = parse_date_time(date_m.group(1).strip())
            data.store("request.date_time", dt.isoformat() if dt else date_m.group(1).strip())
        # Barcode: "Cod cerere: <b>CODE</b>" in raw HTML
        barcode_m = re.search(r'Cod cerere:?\s*<[^>]*>([^<]+)<', header_html)
        if not barcode_m:
            barcode_m = re.search(r'Cod cerere:([A-Z0-9]+)', page_text)
        if barcode_m:
            data.store("request.barcode", barcode_m.group(1).strip())

        if len(row2_cells) >= 3:
            cell0 = row2_cells[0].get_text(strip=True)
            name_m = re.search(r'NUME:(.*?)(?:CNP:|$)', cell0)
            if name_m:
                data.store("patient.name", name_m.group(1).strip())
            cnp_m = re.search(r'CNP:(\d+)', cell0)
            if cnp_m:
                cnp = cnp_m.group(1)
                data.store("patient.cnp", cnp)
                parsed = parse_cnp(cnp)
                data.store("patient.gender", parsed.get("gender"))
                data.store("patient.birth_date", parsed.get("birth_date"))
                data.store("patient.age", parsed.get("age"))

            cell1 = row2_cells[1].get_text(strip=True)
            pid_m = re.search(r'COD PACIENT:(\d+)', cell1)
            if pid_m:
                data.store("patient.id", pid_m.group(1))
            data.store("request.is_urgent", bool(re.search(r'Urgenta:DA', cell1)))

            cell2 = row2_cells[2].get_text(strip=True)
            medic_m = re.search(r'MEDIC:(.*?)$', cell2)
            if medic_m:
                data.store("checkin.medic", medic_m.group(1).strip())

        # Clinical indication: "INFO SUPLIMENTAR: ..." footer note (p.NoteSubsol)
        for note_p in soup.find_all('p', class_='NoteSubsol'):
            note_text = note_p.get_text(' ', strip=True)
            info_m = re.match(r'INFO SUPLIMENTAR:\s*(.+)', note_text, re.IGNORECASE | re.DOTALL)
            if info_m:
                data.store("request.clinical_comments", info_m.group(1))
                break
    except Exception as e:
        logger.warning(f"Error parsing buletin header: {e}")


class HipoClientImagingStudy(HipoClient):
    """Specialized client for imaging study related operations in the Hipocrate medical system.

    Handles retrieval and parsing of medical imaging studies including radiology,
    ultrasound, CT, and MRI examination requests and results.
    """

    def __init__(self, service_url: Optional[str] = None, request: Optional[web.Request] = None):
        """Initialize the service request client."""
        super().__init__(service_url=service_url, request=request)
        self.request_url = "/PARA/Printabile/BuletinAnalize.asp?id={id}&type=2&IdP=1"

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        """Parse a BuletinAnalize type=2 (imaging/radiology) page into HipoData."""
        data = HipoData(status="success", message="")

        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            if not self.is_expected_page(soup, 'BULETIN ANALIZE MEDICALE'):
                data.set_error(f"Unexpected page for ImagingStudy: {self.get_title(soup)}")
                logger.warning(f"{data['message']}: {self.get_error(soup)}")
                return data

            # Parse shared header (same layout as DiagnosticReport)
            _parse_buletin_header(soup, data)

            # Row structure: each study spans 3 consecutive <tr> rows:
            #   Row 1 (class contains "analiza"): study name in the single <td>
            #   Row 2 (td.buletin_2_marit): "Rezultat:" label + result divs
            #   Row 3 (span.conformitate): validation info
            studies = []
            seen = set()
            all_rows = soup.find_all('tr')
            for i, row in enumerate(all_rows):
                if 'analiza' not in row.get('class', []):
                    continue
                study_name = row.get_text(strip=True)
                # Strip "(Tip proba: ...)" suffix for deduplication key
                dedup_key = re.sub(r'\s*\(Tip proba:.*?\)', '', study_name).strip()
                if not dedup_key or dedup_key in seen:
                    continue
                seen.add(dedup_key)
                # Row i+1 is the result row
                result_text = ""
                validation_raw = ""
                if i + 1 < len(all_rows):
                    result_cell = all_rows[i + 1].find('td', class_='buletin_2_marit')
                    if result_cell:
                        # Remove the <b><u>Rezultat:</u></b> label node
                        for tag in result_cell.find_all(['b', 'u']):
                            if 'rezultat' in tag.get_text(strip=True).lower():
                                tag.decompose()
                                break
                        result_text = html_to_markdown(str(result_cell)).strip()
                # Row i+2 is the validation row
                if i + 2 < len(all_rows):
                    validation_raw = all_rows[i + 2].get_text(strip=True)
                date_m = re.search(r'(\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2})?|\d{2}\s+\w+\s+\d{4}(?:\s+\d{2}:\d{2})?)', validation_raw)
                dt = parse_date_time(date_m.group(1)) if date_m else None
                validator_m = re.search(r'Validat de:\s*(.*?)(?:Parafa:|$)', validation_raw)
                validator = validator_m.group(1).strip() if validator_m else None
                study_type, region = identify_study_type_and_region(study_name)
                studies.append({
                    "title": study_name,
                    "result": result_text,
                    "type": study_type,
                    "region": region,
                    "validation_date": dt.isoformat() if dt else None,
                    "validator": validator,
                })
            data.store_list("studies", studies)

            return data

        except Exception as e:
            logger.error(f"Error parsing imaging study data: {e}")
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

            # Add performer: use validator from first study, fall back to requesting medic
            validator = studies[0].get("validator") if studies and isinstance(studies[0], dict) else None
            performer_name = validator or parsed_data.get("checkin.medic")
            if performer_name:
                fhir_imaging_study["performer"] = [{"actor": {"display": performer_name}}]

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

            # Add notes: clinical comments (category=clinical-indication) + per-study results
            notes = []
            if parsed_data.get("request.clinical_comments"):
                notes.append({
                    "text": parsed_data.get("request.clinical_comments"),
                    "category": [{"text": "clinical-indication"}]
                })
            for study in (studies or []):
                if isinstance(study, dict) and study.get("result"):
                    notes.append({"text": study["result"]})
            if notes:
                fhir_imaging_study["note"] = notes

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
        self.request_url = "/PARA/Printabile/BuletinAnalize.asp?id={id}&type=1&IdP=1"

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
        """Parse a BuletinAnalize type=1 (lab diagnostics) page into HipoData."""
        data = HipoData(status="success", message="")

        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            if not self.is_expected_page(soup, 'BULETIN ANALIZE MEDICALE'):
                data.set_error(f"Unexpected page for DiagnosticReport: {self.get_title(soup)}")
                logger.warning(f"{data['message']}: {self.get_error(soup)}")
                return data

            # Parse shared header
            _parse_buletin_header(soup, data)

            # 3-cell data rows: cell0=analysis name, cell1=result, cell2=reference range
            # Section structure (1-cell rows):
            #   "HEMATOLOGIE (device) Starea probei: ..."  → section name (before DENUMIRE header)
            #   "HEMOLEUCOGRAMA (Tip proba: ...)"          → subcategory (after DENUMIRE header)
            #   "Validat de: ..."                          → validator (end of section)
            SKIP_3CELL = ('DENUMIRE ANALIZA', 'NUME:', 'Afisat de:', 'Spitalul ', 'SPITALUL ')
            studies = []
            seen = set()
            section_name = ""
            subcategory = ""
            pending_section = ""   # 1-cell row seen before a DENUMIRE header
            after_header = False   # True immediately after DENUMIRE header row
            for row in soup.find_all('tr'):
                cells = row.find_all('td')
                nc = len(cells)

                if nc == 1:
                    txt = cells[0].get_text(strip=True)
                    if not txt or txt.startswith('Afisat de:') or txt.startswith('Data tiparirii') or txt.startswith('Data eliberarii'):
                        continue
                    if txt.startswith('Validat de:'):
                        # Extract validator for the current section
                        vm = re.search(r'Validat de:\s*(.*?)(?:Parafa:|$)', txt)
                        if vm and studies:
                            # attach validator to last study in this section
                            validator = vm.group(1).strip()
                            for s in reversed(studies):
                                if s.get('section') == section_name:
                                    s['validator'] = validator
                                    break
                        after_header = False
                        pending_section = ""
                        subcategory = ""
                        continue
                    if after_header:
                        # First 1-cell after DENUMIRE header is the subcategory
                        subcategory = re.sub(r'\s*\(Tip proba:.*?\)|\s*\(Metoda de Lucru:.*?\)', '', txt).strip()
                        after_header = False
                    else:
                        # Section name comes before the DENUMIRE header
                        pending_section = re.sub(r'\s*\(.*?\)\s*Starea probei:.*$', '', txt).strip()
                    continue

                if nc == 12:
                    section_name = cells[1].get_text(strip=True)
                    after_header = True
                    subcategory = ""
                    continue

                if nc == 3:
                    cell0_text = cells[0].get_text(strip=True)
                    cell1_text = cells[1].get_text(strip=True)
                    if not cell0_text or any(cell0_text.startswith(p) for p in SKIP_3CELL):
                        if cell0_text == 'DENUMIRE ANALIZA':
                            # Column header — next 1-cell is subcategory
                            if pending_section:
                                section_name = pending_section
                                pending_section = ""
                            after_header = True
                            subcategory = ""
                        continue
                    if 'REZULTAT' == cell0_text or 'Data validare' in cell0_text or 'Data tiparirii' in cell1_text:
                        continue
                    analysis_name = re.sub(r'\s*\(Tip proba:.*?\)|\s*\(Metoda de Lucru:.*?\)|\s*\*.*$', '', cell0_text).strip()
                    reference = cells[2].get_text(strip=True)
                    if not analysis_name or analysis_name in seen:
                        continue
                    seen.add(analysis_name)
                    study_type, region = identify_study_type_and_region(analysis_name)
                    studies.append({
                        "title": analysis_name,
                        "result": cell1_text,
                        "reference": reference,
                        "section": section_name,
                        "subcategory": subcategory,
                        "type": study_type,
                        "region": region
                    })
            data.store_list("studies", studies)

            return data

        except Exception as e:
            logger.error(f"Error parsing diagnostic report data: {e}")
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

            # Clinical indication note (same shape as ImagingStudy, read by the frontend)
            if parsed_data.get("request.clinical_comments"):
                fhir_report["note"] = [{
                    "text": parsed_data.get("request.clinical_comments"),
                    "category": [{"text": "clinical-indication"}]
                }]

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
        self.request_url = "/gen_printabile/BiletExternare.asp?RelId={id}&RelName=CO"

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
        """Parse a Hipocrate BiletExternare (printable discharge form) into HipoData."""
        data = HipoData(status="success", message="")

        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            if not self.is_expected_page(soup, 'Imprimare Fisa'):
                data.set_error("Page is not a discharge summary")
                logger.warning("Page is not a discharge summary")
                return data

            rows = soup.find_all('tr')

            def row_text(r):
                return [c.get_text(strip=True) for c in r.find_all('td')]

            # Row 2: 6-cell — "Data eliberarii:", date, "Sectie / Compartiment:", ward, ...
            # Row 3: 4-cell — "Perioada internarii:", "DD/MM/YYYY HH:MM - DD/MM/YYYY HH:MM", "Medic:", name
            # Row 4: 2-cell — "NUME:SURNAME", "PRENUME:FIRSTNAME"
            # Row 5: 2-cell — "DIAGNOSTIC PRINCIPAL (DRG Cod 1):code desc", "DIAGNOSTIC PRINCIPAL (DRG Cod 2):-"
            # Row 6: 2-cell — "VARSTA:...", "CNP:..."
            # Row 10: 2-cell — "STAREA LA EXTERNARE:..."
            # Row 11-12: secondary diagnoses
            # Row 13: 1-cell "EPICRIZA" header; Row 14: 1-cell epicrisis text
            # Row 15: 1-cell "TRATAMENT RECOMANDAT"; Row 16: 1-cell "RECOMANDARI..."; Row 17: recommendations

            for i, row in enumerate(rows):
                cells = row_text(row)
                nc = len(cells)

                if nc == 6 and cells[0] == 'Data eliberarii:':
                    data.store("checkout.date", cells[1])
                    data.store("checkout.ward", cells[3])
                    fo_m = re.search(r'FO\s*(\d+)', cells[4])
                    if fo_m:
                        data.store("checkout.fo_number", fo_m.group(1))
                    data.store("checkout.is_urgent", 'UrgentaDA' in cells[5] or 'Urgenta DA' in cells[5])

                elif nc == 4 and cells[0] == 'Perioada internarii:':
                    period = cells[1]
                    data.store("checkin.medic", re.sub(r'^Dr\.', '', cells[3]).strip())
                    # "DD/MM/YYYY HH:MM - DD/MM/YYYY HH:MM"
                    m = re.match(r'(\S+\s+\S+)\s*-\s*(\S+\s+\S+)', period)
                    if m:
                        data.store("checkin.date_time", m.group(1))
                        data.store("checkout.date_time", m.group(2))

                elif nc == 2 and cells[0].startswith('NUME:'):
                    surname = cells[0][len('NUME:'):]
                    firstname = cells[1][len('PRENUME:'):] if cells[1].startswith('PRENUME:') else cells[1]
                    data.store("patient.name", f"{surname} {firstname}".strip())

                elif nc == 2 and cells[0].startswith('DIAGNOSTIC PRINCIPAL (DRG Cod 1):'):
                    data.store("checkin.diagnosis", cells[0][len('DIAGNOSTIC PRINCIPAL (DRG Cod 1):'):].strip())

                elif nc == 2 and cells[1].startswith('CNP:'):
                    cnp = cells[1][len('CNP:'):]
                    data.store("patient.cnp", cnp)
                    parsed = parse_cnp(cnp)
                    data.store("patient.gender", parsed.get("gender"))
                    data.store("patient.date", parsed.get("birth_date"))
                    data.store("patient.age", parsed.get("age"))

                elif nc == 2 and 'CASA ASIGURARE:' in cells[0]:
                    data.store("patient.insurance_house", cells[0].split('CASA ASIGURARE:',1)[1].strip())
                    if 'CATEGORIA DE ASIGURAT:' in cells[1]:
                        data.store("patient.insurance_category", cells[1].split('CATEGORIA DE ASIGURAT:',1)[1].strip())

                elif nc == 2 and 'NUMAR DE ASIGURAT:' in cells[0]:
                    data.store("patient.insurance_number", cells[0].split('NUMAR DE ASIGURAT:',1)[1].strip())
                    if 'ADRESA:' in cells[1]:
                        data.store("patient.address", cells[1].split('ADRESA:',1)[1].strip())

                elif nc == 2 and 'TELEFON:' in cells[0]:
                    data.store("patient.phone", cells[0].split('TELEFON:',1)[1].strip())

                elif nc == 2 and cells[0].startswith('STAREA LA EXTERNARE:'):
                    data.store("checkout.discharge_status", cells[0][len('STAREA LA EXTERNARE:'):].strip())

                elif nc == 1 and cells[0] == 'EPICRIZA':
                    # Next non-empty 1-cell row is the epicrisis text.
                    # Use inner HTML + html_to_markdown so paragraph structure is preserved;
                    # get_text(strip=True) would collapse all formatting to a single line.
                    for j in range(i + 1, min(i + 5, len(rows))):
                        nxt = row_text(rows[j])
                        if len(nxt) == 1 and nxt[0] and nxt[0] not in ('TRATAMENT RECOMANDAT', 'RECOMANDARI / REGIM / MEDICATIE'):
                            cell = rows[j].find('td')
                            cell_html = cell.decode_contents() if cell else nxt[0]
                            data.store("checkout.epicrisis", html_to_markdown(cell_html))
                            break

                elif nc == 1 and cells[0] == 'TRATAMENT RECOMANDAT':
                    for j in range(i + 1, min(i + 5, len(rows))):
                        nxt = row_text(rows[j])
                        if len(nxt) == 1 and nxt[0] and nxt[0] not in ('RECOMANDARI / REGIM / MEDICATIE',):
                            cell = rows[j].find('td')
                            cell_html = cell.decode_contents() if cell else nxt[0]
                            data.store("checkout.treatment", html_to_markdown(cell_html))
                            break

                elif nc == 1 and cells[0] == 'RECOMANDARI / REGIM / MEDICATIE':
                    for j in range(i + 1, min(i + 5, len(rows))):
                        nxt = row_text(rows[j])
                        if len(nxt) == 1 and nxt[0] and not nxt[0].startswith('EXAMENE'):
                            cell = rows[j].find('td')
                            cell_html = cell.decode_contents() if cell else nxt[0]
                            data.store("checkout.recommendations", html_to_markdown(cell_html))
                            break

                elif nc == 2 and cells[0].startswith('DIAGNOSTICE SECUNDARE'):
                    # Next row contains codes concatenated: "P92.0 Voma la nou-nascutR63.3 ..."
                    for j in range(i + 1, min(i + 3, len(rows))):
                        nxt = row_text(rows[j])
                        if len(nxt) >= 1 and nxt[0] and nxt[0] != '-':
                            # Split on ICD-10 code boundary: letter+digit+dot preceded by non-space
                            raw = nxt[0]
                            parts = re.split(r'(?<=[a-zA-Z])(?=[A-Z]\d{2}\.)', raw)
                            secondary = [p.strip() for p in parts if p.strip() and p.strip() != '-']
                            if secondary:
                                data.store_list("checkin.secondary_diagnoses", secondary)
                            break

            # Extract 2-cell lab/imaging investigation rows under section headers
            investigations = []
            current_section = ""
            for row in rows:
                cells = row_text(row)
                if len(cells) == 1:
                    txt = cells[0]
                    if txt.startswith('EXAMENE') or txt.startswith('PROCEDURI'):
                        current_section = txt
                elif len(cells) == 2 and cells[0] not in ('COD CERERE / DATA',) and current_section:
                    code_date = cells[0]
                    detail = cells[1]
                    if code_date and detail:
                        investigations.append({
                            "section": current_section,
                            "code_date": code_date,
                            "detail": detail
                        })
            if investigations:
                data.store_list("investigations", investigations)

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

            # Emergency flag
            if parsed_data.get("checkout.is_urgent"):
                fhir_encounter["priority"] = {
                    "coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ActPriority", "code": "EM", "display": "emergency"}]
                }

            # FO number as identifier
            fo_number = parsed_data.get("checkout.fo_number")
            if fo_number:
                fhir_encounter["identifier"] = [{"system": "FO", "value": fo_number}]

            # Insurance
            if parsed_data.get("patient.insurance_house"):
                fhir_encounter["extension"] = fhir_encounter.get("extension", [])
                fhir_encounter["extension"].append({
                    "url": "insurance",
                    "valueString": parsed_data.get("patient.insurance_house")
                })
                if parsed_data.get("patient.insurance_category"):
                    fhir_encounter["extension"].append({
                        "url": "insuranceCategory",
                        "valueString": parsed_data.get("patient.insurance_category")
                    })

            # Patient contact info
            if parsed_data.get("patient.address") or parsed_data.get("patient.phone"):
                fhir_encounter["extension"] = fhir_encounter.get("extension", [])
                if parsed_data.get("patient.address"):
                    fhir_encounter["extension"].append({"url": "patientAddress", "valueString": parsed_data.get("patient.address")})
                if parsed_data.get("patient.phone"):
                    fhir_encounter["extension"].append({"url": "patientPhone", "valueString": parsed_data.get("patient.phone")})

            # Notes: epicrisis + recommended treatment
            notes = []
            epicrisis = parsed_data.get("checkout.epicrisis")
            if epicrisis:
                notes.append({"text": epicrisis})
            treatment = parsed_data.get("checkout.treatment")
            if treatment:
                notes.append({"text": f"[Treatment] {treatment}"})
            if notes:
                fhir_encounter["note"] = notes

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

            # Secondary diagnoses
            secondary = parsed_data.get("checkin.secondary_diagnoses") or []
            if secondary:
                if "diagnosis" not in fhir_encounter:
                    fhir_encounter["diagnosis"] = []
                for idx, diag in enumerate(secondary):
                    fhir_encounter["diagnosis"].append({
                        "condition": {
                            "reference": f"Condition/secondary-{encounter_id}-{idx}",
                            "display": diag
                        },
                        "use": {
                            "coding": [{
                                "system": "http://terminology.hl7.org/CodeSystem/diagnosis-role",
                                "code": "CM",
                                "display": "Comorbidity diagnosis"
                            }]
                        }
                    })

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


class HipoClientCheckin(HipoClient):
    """Parses the admission record (/files/checkin.asp?id={id})."""

    def __init__(self, service_url=None, request=None):
        super().__init__(service_url=service_url, request=request)
        self.request_url = "/files/checkin.asp?id={id}"

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        data = HipoData(status="success", message="")
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            if not self.is_expected_page(soup, 'FISA INTERNARE'):
                data.set_error(f"Unexpected page for Checkin: {self.get_title(soup)}")
                logger.warning(data['message'])
                return data

            rows = soup.find_all('tr')

            def rt(r):
                return [c.get_text(' ', strip=True) for c in r.find_all('td')]

            for i, row in enumerate(rows):
                cells = rt(row)
                nc = len(cells)

                # Row 5: "Pacient [ NAME ] CNP ..." + "Prezentare [ id ] Data: ... Urgenta: ... Sectie: ..."
                if nc >= 1 and cells[0].startswith('Pacient ['):
                    m = re.search(r'Pacient\s*\[\s*(.*?)\s*\]\s*CNP\s+(\S+)', cells[0])
                    if m:
                        data.store("patient.name", m.group(1).strip())
                        data.store("patient.cnp", m.group(2))
                        parsed = parse_cnp(m.group(2))
                        data.store("patient.gender", parsed.get("gender"))
                        data.store("patient.date", parsed.get("birth_date"))
                        data.store("patient.age", parsed.get("age"))
                    if nc >= 2:
                        m2 = re.search(r'Prezentare\s*\[\s*(\S+)\s*\]\s*Data:\s*(\S+\s+\S+)\s*Urgenta:\s*(\S+)\s*Sect\w*:\s*(\S+)', cells[1])
                        if m2:
                            data.store("presentation.id", m2.group(1))
                            data.store("presentation.date_time", m2.group(2))
                            data.store("presentation.is_urgent", m2.group(3).upper() == 'DA')
                            data.store("presentation.section", m2.group(4))

                # Row 19: "Tip diagnostic: Cronic Acut Subacut Ore de ventilatie:"
                elif nc == 1 and cells[0].startswith('Tip diagnostic:'):
                    tip_raw = cells[0][len('Tip diagnostic:'):].strip()
                    # Strip the radio-button labels — only keep before "Ore de ventilatie"
                    tip = re.sub(r'\s*Ore de ventilatie:.*$', '', tip_raw).strip()
                    data.store("checkin.diagnosis_type", tip)

                # Row 20: "Diagnostic DRG la internare: CODE desc"
                elif nc == 1 and cells[0].startswith('Diagnostic DRG la internare:'):
                    data.store("checkin.diagnosis", cells[0][len('Diagnostic DRG la internare:'):].strip())

                # Row 21: "Diagnostic la 72H: ..."
                elif nc == 1 and cells[0].startswith('Diagnostic la 72H:'):
                    val = cells[0][len('Diagnostic la 72H:'):].strip()
                    if val:
                        data.store("checkin.diagnosis_72h", val)

                # Row 22: "Diagnostice secundare" header → next rows with section/regim/de la/pana la
                elif nc == 1 and cells[0].strip() == 'Diagnostice secundare':
                    secondary = []
                    for j in range(i + 1, min(i + 10, len(rows))):
                        nxt = rt(rows[j])
                        if len(nxt) >= 1 and nxt[0] in ('Sectia', 'Cod', 'Examen general:', ''):
                            break
                        if len(nxt) >= 1 and nxt[0].strip() and not nxt[0].startswith('['):
                            parts = re.split(r'(?<=[a-zA-Z])(?=[A-Z]\d{2}\.)', nxt[0])
                            for p in parts:
                                p = p.strip()
                                if p and p not in ('Sectia', 'Regim', 'De la', 'Pana la'):
                                    secondary.append(p)
                    if secondary:
                        data.store_list("checkin.secondary_diagnoses", secondary)

                # Ward transfers: "Cod | Sectie | Medic | Data/Ora | Tip Examinare | Decizie | _"
                # Skip header rows and lab history rows
                elif (nc == 7 and cells[0] not in ('Cod', 'Nr.Crt.', 'Laborator', '')
                      and cells[1] not in ('Sectie', 'Cod cerere', '')
                      and cells[2] not in ('Medic', 'Data recoltarii', '')):
                    transfers = data.get("checkin.transfers") or []
                    transfers.append({
                        "section": cells[1].strip(),
                        "medic": cells[2].strip(),
                        "date_time": cells[3].strip(),
                        "type": cells[4].strip(),
                        "decision": cells[5].strip(),
                    })
                    data.store_list("checkin.transfers", transfers)

                # Physical exam
                elif nc == 2 and cells[0] == 'Examen general:':
                    data.store("checkin.exam_general", cells[1].strip())
                elif nc == 2 and cells[0] == 'Examen local:':
                    data.store("checkin.exam_local", cells[1].strip())

            if 'id' in kwargs:
                data.store("checkin.id", kwargs["id"])

            return data
        except Exception as e:
            logger.error(f"Error parsing checkin data: {e}")
            data.set_error(str(e))
            return data

    def fhir_response(self, parsed_data: HipoData, **kwargs) -> Union[FHIREncounter, FHIROperationOutcome]:
        """Convert parsed checkin HipoData to a FHIR Encounter resource (status=in-progress)."""
        try:
            if parsed_data.get("status") == "error":
                return FHIROperationOutcome.from_error(
                    message=parsed_data.get("message", "Error in parsed checkin data"),
                    code="processing",
                    severity="error"
                )

            encounter_id = parsed_data.get('checkin.id', '')
            fhir_encounter = FHIREncounter(
                id=encounter_id,
                status="in-progress",
                type=[{
                    "coding": [{
                        "system": "http://snomed.info/sct",
                        "code": "305056002",
                        "display": "Admission to hospital"
                    }]
                }],
                subject={
                    "reference": f"Patient/{parsed_data.get('patient.id', '')}"
                }
            )

            # Attending physician from first transfer row or checkin.medic
            medic = parsed_data.get("checkin.medic")
            if not medic:
                transfers = parsed_data.get("checkin.transfers") or []
                if transfers:
                    medic = transfers[0].get("medic")
            if medic:
                fhir_encounter["participant"] = [{
                    "type": [{
                        "coding": [{
                            "system": "http://terminology.hl7.org/CodeSystem/v3-ParticipationType",
                            "code": "ATND",
                            "display": "attender"
                        }]
                    }],
                    "individual": {"display": medic}
                }]

            # Admission period — start only (still in progress)
            checkin_datetime = parsed_data.get("checkin.date_time") or parsed_data.get("presentation.date_time")
            if checkin_datetime:
                dt = parse_date_time(checkin_datetime)
                fhir_encounter["period"] = {"start": dt.isoformat() if dt else checkin_datetime}

            # Ward / location from transfers (most recent) or presentation.section
            section = None
            transfers = parsed_data.get("checkin.transfers") or []
            if transfers:
                section = transfers[-1].get("section")
            if not section:
                section = parsed_data.get("presentation.section")
            if section:
                fhir_encounter["location"] = [{
                    "location": {"display": section},
                    "status": "active"
                }]

            # Admission diagnosis
            diagnosis = parsed_data.get("checkin.diagnosis")
            if diagnosis:
                fhir_encounter["reasonCode"] = [{"text": diagnosis}]
                fhir_encounter["diagnosis"] = [{
                    "condition": {
                        "reference": f"Condition/admission-{encounter_id}",
                        "display": diagnosis
                    },
                    "use": {
                        "coding": [{
                            "system": "http://terminology.hl7.org/CodeSystem/diagnosis-role",
                            "code": "AD",
                            "display": "Admission diagnosis"
                        }]
                    }
                }]

            # Urgency
            if parsed_data.get("presentation.is_urgent"):
                fhir_encounter["priority"] = {
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/v3-ActPriority",
                        "code": "EM",
                        "display": "emergency"
                    }]
                }

            # Physical exam notes
            notes = []
            if parsed_data.get("checkin.exam_general"):
                notes.append({"text": f"[Exam general] {parsed_data.get('checkin.exam_general')}"})
            if parsed_data.get("checkin.exam_local"):
                notes.append({"text": f"[Exam local] {parsed_data.get('checkin.exam_local')}"})
            if notes:
                fhir_encounter["note"] = notes

            return fhir_encounter
        except Exception as e:
            logger.error(f"Error converting checkin data to FHIR: {e}")
            return FHIROperationOutcome.from_exception(e, code="exception")

    async def fetch_respond_fhir(self, **kwargs) -> Union[FHIREncounter, FHIROperationOutcome]:
        parsed = await self.fetch_and_parse(**kwargs)
        return self.fhir_response(parsed, **kwargs)


class HipoClientCheckup(HipoClient):
    """Parses the emergency/outpatient consultation (/files/checkup.asp?cuid={id})."""

    def __init__(self, service_url=None, request=None):
        super().__init__(service_url=service_url, request=request)
        self.request_url = "/files/checkup.asp?cuid={id}"

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        data = HipoData(status="success", message="")
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            if not self.is_expected_page(soup, 'Consult'):
                data.set_error(f"Unexpected page for Checkup: {self.get_title(soup)}")
                logger.warning(data['message'])
                return data

            rows = soup.find_all('tr')

            def rt(r):
                return [c.get_text(' ', strip=True) for c in r.find_all('td')]

            for i, row in enumerate(rows):
                cells = rt(row)
                nc = len(cells)

                # Row 5 (3-cell): patient + presentation + admission
                if nc >= 2 and cells[0].startswith('Pacient ['):
                    m = re.search(r'Pacient\s*\[\s*(.*?)\s*\]\s*CNP\s+(\S+)', cells[0])
                    if m:
                        data.store("patient.name", m.group(1).strip())
                        data.store("patient.cnp", m.group(2))
                        parsed = parse_cnp(m.group(2))
                        data.store("patient.gender", parsed.get("gender"))
                        data.store("patient.date", parsed.get("birth_date"))
                        data.store("patient.age", parsed.get("age"))
                    m2 = re.search(r'Prezentare\s*\[\s*(\S+)\s*\]\s*Data:\s*(\S+\s+\S+)\s*Urgenta:\s*(\S+)\s*Sect\w*:\s*(\S+)', cells[1] if nc > 1 else '')
                    if m2:
                        data.store("presentation.date_time", m2.group(2))
                        data.store("presentation.is_urgent", m2.group(3).upper() == 'DA')
                        data.store("presentation.section", m2.group(4))
                    if nc >= 3:
                        m3 = re.search(r'Internare\s*\[\s*(\S+)\s*\]\s*Data:\s*(\S+\s+\S+)\s*Sectie:\s*(\S+)\s*Medic:\s*(.*)', cells[2])
                        if m3:
                            data.store("checkin.id", m3.group(1))
                            data.store("checkin.date_time", m3.group(2))
                            data.store("checkin.section", m3.group(3))
                            data.store("checkin.medic", m3.group(4).strip())

                # Diagnostic ICD10 + text
                elif nc == 4 and cells[0] == 'Diagnostic ICD10:':
                    data.store("diagnosis.icd10", cells[1].strip())
                    data.store("diagnosis.text", cells[3].strip())

                # Initial / final diagnosis
                elif nc == 4 and cells[0] == 'Diagnostic initial:':
                    data.store("diagnosis.initial", cells[1].strip())
                    data.store("diagnosis.final", cells[3].strip())

                # Referral diagnosis
                elif nc >= 2 and cells[0] == 'Diagnostic trimitere:':
                    data.store("diagnosis.referral", cells[1].strip())

                # Discharge state
                elif nc >= 1 and 'Stare pacient' in cells[0]:
                    # Value follows in next non-empty cell
                    for c in cells[1:]:
                        if c.strip() and c.strip() not in ('50-Ameliorat', '51-Stationar', '52-Agravat', '53-Decedat'):
                            break
                    # Parse from the row text: look for selected value
                    row_text = row.get_text(' ', strip=True)
                    for state in ('Ameliorat', 'Stationar', 'Agravat', 'Decedat'):
                        if state.lower() in row_text.lower():
                            data.store("discharge.status", state.lower())
                            break

                # Exam general / local
                elif nc == 4 and cells[0] == 'Examen clinic general:':
                    data.store("exam.general", cells[1].strip())
                    data.store("exam.local", cells[3].strip())

            if 'id' in kwargs:
                data.store("checkup.id", kwargs["id"])

            return data
        except Exception as e:
            logger.error(f"Error parsing checkup data: {e}")
            data.set_error(str(e))
            return data


class HipoClientCerere(HipoClient):
    """Fetches a request edit page (cerere.asp) and extracts the patient ID."""

    def __init__(self, service_url=None, request=None):
        super().__init__(service_url=service_url, request=request)
        self.request_url = "/PARA/NOM/Listare/cerere.asp?id={id}"

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        data = HipoData(status="success", message="")
        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            # Patient ID
            ids = extract_ids_from_links(soup, r'[Pp]acient/edit\.asp\?id=(\d+)')
            if ids:
                data.store("patient.id", ids[0])
            else:
                data.set_error("Patient ID not found in request page")

            # Exam names — try three patterns in priority order:

            exams = []
            seen = set()

            def add_exam(text):
                t = text.strip()
                if t and t not in seen:
                    seen.add(t)
                    exams.append(t)

            # Pattern 1: numbered rows (same as buletinRecoltari) — cell[0] is digit, cell[1] is name
            for row in soup.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) >= 2 and cells[0].get_text(strip=True).isdigit():
                    add_exam(cells[1].get_text(strip=True))

            # Pattern 2: checked checkboxes with an associated label or adjacent text node
            if not exams:
                for cb in soup.find_all('input', {'type': 'checkbox', 'checked': True}):
                    label = cb.find_next_sibling(string=True) or ''
                    if not label:
                        lbl_el = cb.find_next('label') or cb.find_parent('label')
                        label = lbl_el.get_text(strip=True) if lbl_el else ''
                    add_exam(str(label))

            # Pattern 3: <label> elements whose for= matches a checked checkbox id
            if not exams:
                checked_ids = {
                    cb.get('id') for cb in soup.find_all('input', {'type': 'checkbox', 'checked': True})
                    if cb.get('id')
                }
                for lbl in soup.find_all('label'):
                    if lbl.get('for') in checked_ids:
                        add_exam(lbl.get_text(strip=True))

            if exams:
                data.store_list("exams", exams)

            return data
        except Exception as e:
            logger.error(f"Error parsing cerere data: {e}")
            data.set_error(str(e))
            return data


class HipoClientWhoami(HipoClient):
    """Extracts the logged-in user identity from the sidebar menu iframe
    (Template/menu.asp), CONTUL MEU / Informatii personale section."""

    def __init__(self, service_url=None, request=None):
        super().__init__(service_url=service_url, request=request)
        self.request_url = "Template/menu.asp"

    async def fetch_and_parse(self, *args, **kwargs):
        # The menu page is the same URL for every user but its content is
        # user-specific — it must never be served from or left in the shared URL cache.
        menu_url = self.get_full_url(self.request_url)
        self.cache_remove(menu_url)
        parsed_data = await super().fetch_and_parse(*args, **kwargs)
        self.cache_remove(menu_url)
        return parsed_data

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        """Parse the CONTUL MEU section of the menu iframe.

        It carries the display name in a <small> tag ("[ DR. STROIE COSTIN ]")
        and a cont.asp?id= link ("Informatii personale") with the user ID.
        """
        data = HipoData(status="success", message="")
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            found = False
            for small in soup.find_all('small'):
                td = small.find_parent('td', class_='menu_caps')
                if td and 'CONTUL MEU' in td.get_text():
                    name = small.get_text(' ', strip=True).replace('\xa0', ' ')
                    name = re.sub(r'\s+', ' ', name).strip('[] ').strip()
                    # Blank name means the anonymous (logged-out) menu variant
                    if name:
                        found = True
                        data.store("user.display_name", name)
                    break
            ids = extract_ids_from_links(soup, r'cont\.asp\?id=(\d+)')
            if ids:
                found = True
                data.store("user.id", ids[0])
            if not found:
                data.set_error("User identity not found on Hipocrate menu page")
                return data
            # The login username is the authoritative account name; the menu
            # page does not repeat it anywhere parseable.
            if self.username:
                data.store("user.username", self.username)
            return data
        except Exception as e:
            logger.error(f"Error parsing whoami data: {e}")
            data.set_error(str(e))
            return data


class HipoClientSchedule(HipoClient):
    """Parses the daily imaging/lab request worklist (/PARA/NOM/Listare/?id=44)."""

    @staticmethod
    def _lab_to_modality(lab: str) -> Optional[str]:
        """Map Hipocrate laboratory label to a modality slug."""
        l = lab.lower().strip()
        if 'ecografie' in l:                            return 'eco'
        if 'radioscopii' in l:                          return 'fluoro'
        if 'radiografie' in l:                          return 'radio'
        if 'tomografie' in l or 'computerizata' in l:   return 'ct'
        if 'computer tomograf' in l:                    return 'ct'
        if l == 'ct' or l.startswith('ct '):            return 'ct'
        if 'imagistica' in l or 'rezonanta' in l:       return 'irm'
        if 'laborator' in l:                            return 'lab'
        return None

    def __init__(self, service_url=None, request=None):
        super().__init__(service_url=service_url, request=request)
        self.request_url = "/PARA/NOM/Listare/"

    def _build_url(self, start_date=None, end_date=None, lab_id=None, patient_text=None, limit=None):
        def _fmt(date_str):
            if date_str:
                return datetime.strptime(date_str, '%Y-%m-%d').strftime('%d/%m/%Y')
            return datetime.now().strftime('%d/%m/%Y')
        sd = _fmt(start_date)
        ed = _fmt(end_date or start_date)
        per_page = int(limit) if limit and str(limit).isdigit() else 200
        url = (self.request_url +
               f"?id=44&NrPePag={per_page}"
               f"&LR_requesteddateSD={sd}"
               f"&LR_requesteddateED={ed}"
               f"&PARA_ID_Laborator={lab_id or ''}"
               f"&PARA_TextCautare={patient_text or ''}"
               f"&PARA_ID_TipCautare={'2' if patient_text else ''}"
               f"&PARA_Ordonare=2")
        return url

    async def fetch_and_parse(self, **kwargs) -> HipoData:
        data = HipoData(status="success", message="")
        url = self._build_url(
            kwargs.get('start_date') or kwargs.get('date'),
            kwargs.get('end_date'),
            lab_id=kwargs.get('lab_id'),
            patient_text=kwargs.get('patient_text'),
            limit=kwargs.get('limit'),
        )
        if kwargs.get('force'):
            self.cache_remove(self.get_full_url(url))
        try:
            response_text, error_message = await self.get_page(url)
            if error_message:
                data.set_error(error_message)
                return data
            return self.parse_data(response_text, **kwargs)
        except Exception as e:
            logger.error(f"fetch_and_parse (schedule) failed: {e}")
            data.set_error(f"Data retrieval failed: {e}")
            return data

    async def debug_page(self, **kwargs):
        url = self._build_url(
            kwargs.get('start_date') or kwargs.get('date'),
            kwargs.get('end_date'),
            lab_id=kwargs.get('lab_id'),
            patient_text=kwargs.get('patient_text'),
        )
        try:
            response_text, error_message = await self.get_page(url)
            if error_message:
                return f"Page error: {error_message}"
            return response_text
        except Exception as e:
            return f"Page retrieval failed: {str(e)}"

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        data = HipoData(status="success", message="")
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            table = soup.find('table', class_='tbl_listare')
            if not table:
                data.set_error("Unexpected page: tbl_listare table not found")
                return data

            requests = []
            for row in table.find_all('tr'):
                cells = row.find_all('td', class_='tdn')
                if len(cells) < 3:
                    continue
                patient_name = cells[0].get_text(strip=True)
                code_link = cells[1].find('a')
                if not code_link:
                    continue
                request_code = code_link.get_text(strip=True)
                id_match = re.search(r'id=(\d+)', code_link.get('href', ''))
                request_id = id_match.group(1) if id_match else None

                # Inner table has a header row then a data row; take the last tr
                detail_rows = cells[2].select('div.div_detalii table tr')
                detail_cells = detail_rows[-1].find_all('td') if detail_rows else []
                if len(detail_cells) >= 7:
                    raw_dt = detail_cells[0].get_text(strip=True)
                    parsed_dt = parse_date_time(raw_dt)
                    iso_dt = parsed_dt.strftime('%Y-%m-%d %H:%M') if parsed_dt else raw_dt
                    requests.append({
                        'patient_name': patient_name,
                        'request_code': request_code,
                        'request_id': request_id,
                        'date_time': iso_dt,
                        'status': detail_cells[1].get_text(strip=True),
                        'payment_type': detail_cells[2].get_text(strip=True),
                        'priority': detail_cells[3].get_text(strip=True),
                        'section': detail_cells[4].get_text(strip=True),
                        'requested_by': detail_cells[5].get_text(strip=True),
                        'laboratory': detail_cells[6].get_text(strip=True),
                    })

            data.store_list("requests", requests)
            data.store("total", len(requests))
            return data
        except Exception as e:
            logger.error(f"Error parsing schedule data: {e}")
            data.set_error(str(e))
            return data

    # Maps Hipocrate status text → FHIR ServiceRequest.status
    _FHIR_STATUS = {
        'cerere netrimisa':                   'on-hold',
        'trimisa in laborator':               'draft',
        'primita in laborator':               'draft',
        'in lucru(nv)':                       'active',
        'fara analize':                       'entered-in-error',
        'cerere completata':                  'completed',
        'cerere completata/partial validata': 'completed',
        'terminata':                          'ended',
    }

    def fhir_response(self, parsed_data: HipoData, **kwargs) -> Union[FHIRBundle, FHIROperationOutcome]:
        """Convert parsed schedule HipoData to a FHIR Bundle of ServiceRequest resources."""
        http_request = kwargs.get('http_request', self.request)
        try:
            if parsed_data.get("status") == "error":
                return FHIROperationOutcome.from_error(
                    message=parsed_data.get("message", "Error retrieving schedule"),
                    code="processing",
                    severity="error"
                )

            requests = parsed_data.get("requests") or []

            # Python-side filtering for section (by name; lab is filtered natively by Hipocrate via PARA_ID_Laborator)
            section_name = (kwargs.get('section_name') or '').strip()
            if section_name:
                requests = [r for r in requests if (r.get('section') or '') == section_name]

            bundle = FHIRBundle(type="searchset", total=len(requests))

            system_base = (
                f"{http_request.scheme}://{http_request.host}"
                if http_request else "http://localhost"
            )

            for req in requests:
                status_key = (req.get('status') or '').lower()
                fhir_status = self._FHIR_STATUS.get(status_key, 'unknown')
                priority = 'urgent' if (req.get('priority') or '').lower() not in ('normala', 'normal', '') else 'routine'

                sr = FHIRServiceRequest(
                    id=req.get('request_id'),
                    status=fhir_status,
                    intent="order",
                    priority=priority,
                    identifier=[{
                        "system": f"{system_base}/fhir/NamingSystem/request-code",
                        "value": req.get('request_code'),
                    }] if req.get('request_code') else None,
                    subject=FHIRReference(display=req.get('patient_name')),
                    code=FHIRCodeableConcept(text=req.get('laboratory')),
                    category=[FHIRCodeableConcept(coding=[{"code": modality}])] if (modality := self._lab_to_modality(req.get('laboratory') or '')) else None,
                    authoredOn=req.get('date_time'),
                    requester=FHIRReference(display=req.get('requested_by')) if req.get('requested_by') else None,
                    note=[n for n in [
                        {"text": req.get('section')} if req.get('section') else None,
                        {"text": req.get('payment_type')} if req.get('payment_type') else None,
                    ] if n] or None,
                )
                bundle.append_entry(resource=sr)

            return bundle
        except Exception as e:
            logger.error(f"Error building FHIR schedule bundle: {e}")
            return FHIROperationOutcome.from_exception(e, code="exception")

    async def fetch_respond_fhir(self, **kwargs) -> Union[FHIRBundle, FHIROperationOutcome]:
        parsed = await self.fetch_and_parse(**kwargs)
        if parsed.get("status") == "error":
            return FHIROperationOutcome.from_error(
                message=parsed.get("message", "Unknown error"),
                code="processing",
                severity="error"
            )
        return self.fhir_response(parsed, **kwargs)
