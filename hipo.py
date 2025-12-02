#!/usr/bin/env python3
"""Hipocrate medical system data retrieval client implementation.

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

import asyncio
import aiohttp
from aiohttp import web, BasicAuth
from yarl import URL
import logging
import re
from bs4 import BeautifulSoup, Comment
import html
from datetime import datetime, timedelta
import configparser

from typing import Any, Dict, List, Optional


from extractors import extract_id_from_link, extract_ids_from_links, extract_text_ids_from_links, extract_selected_from_dropdown, extract_tabular_data, extract_text_after_label, extract_text_from_element, extract_textarea_after_label, extract_value_from_input
from extractors import parse_cnp

from markdown import html_to_markdown, markdown_to_html

# Import FHIR classes
from fhir import ServiceRequest as FHIRServiceRequest, CodeableConcept, Reference, Patient as FHIRPatient

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)8s | %(message)s'
)
logger = logging.getLogger('HipoClient')

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






# Headers for compatibility with Hipocrate service
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ro-RO,ro;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


def contains_any_word(string, *words):
    """
    Check if any of the specified words are present in the given string.

    Args:
        string: String to search in
        *words: Variable number of words to search for

    Returns:
        bool: True if any word is found in the string, False otherwise
    """
    return any(i in string.lower() for i in words)


def identify_study_type_and_region(desc: str) -> tuple:
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
    
    desc_lower = desc.lower()
    
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
        if contains_any_word(desc_lower, *keywords):
            region = region_key
            break
    
    return study_type, region


def parse_date_time(date_str: str) -> Optional[datetime]:
    """Parse a date string in the format '30 Aug 2025 19:25:00'.

    Handles common date formats used in medical records including both English
    and Romanian month abbreviations.

    Args:
        date_str: Date string to parse in format like "30 Aug 2025 19:25:00"

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


def create_error_response(message: str, status_code: int = 400, details: Dict[str, Any] = None) -> web.Response:
    """Create a standardized error response for web API endpoints.

    Generates consistent JSON error responses with appropriate logging based
    on the HTTP status code (error level for 5xx, warning for 4xx).

    Args:
        message: Error message to include in response
        status_code: HTTP status code (default: 400)
        details: Additional error details to include in response

    Returns:
        Standardized JSON error response as web.Response
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



class URLCache:
    """Simple in-memory cache for HTTP responses with LRU eviction and timeout.

    Implements a basic Least Recently Used (LRU) cache for storing HTTP response
    content with automatic expiration based on configurable timeout periods.
    """

    def __init__(self, max_size: int = 100, timeout: int = 600):
        """Initialize the cache.

        Args:
            max_size: Maximum number of entries to cache (default: 100)
            timeout: Cache timeout in seconds (default: 600 seconds/10 minutes)
        """
        self.max_size = max_size
        self.timeout = timeout
        self.cache: Dict[str, str] = {}
        self.timestamps: Dict[str, datetime] = {}

    def get(self, url: str) -> Optional[str]:
        """Get cached response for URL if exists and not expired.

        Retrieves cached content for a URL if it exists and hasn't expired
        based on the configured timeout value.

        Args:
            url: URL to lookup in cache

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

        Stores response text in cache with current timestamp. If cache is at
        maximum capacity, the oldest entry is automatically removed.

        Args:
            url: URL key for caching
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
        """Remove specific cache entry.

        Removes a specific URL's cached content if it exists.

        Args:
            url: Specific URL to remove from cache
        """
        if url:
            if url in self.cache:
                del self.cache[url]
            if url in self.timestamps:
                del self.timestamps[url]

    def clear(self) -> None:
        """Clear all cache entries.

        Removes all cached content from the cache.
        """
        self.cache.clear()
        self.timestamps.clear()


# Simple in-memory cache for HTTP responses
url_cache = URLCache(max_size=100, timeout=10 * 60)

# Simple in-memory cache for CNP to patient code mappings
cnp_cache: Dict[str, str] = {}
cache_max_size = 1000  # Maximum number of entries to cache



class UserSessionManager:
    """Manager for user-specific HTTP sessions with automatic cookie handling.

    Handles creation, storage, and cleanup of aiohttp ClientSessions for
    individual users, ensuring proper cookie management and resource cleanup.
    """

    def __init__(self):
        """Initialize the user session manager."""
        self.user_sessions: Dict[str, aiohttp.ClientSession] = {}

    def get_user_session(self, username: str):
        """Get or create a user-specific session with cookie support.

        Retrieves an existing session for a user or creates a new one with
        automatic cookie handling enabled.

        Args:
            username: Username to get session for

        Returns:
            aiohttp.ClientSession for the user with cookie jar enabled
        """
        if username not in self.user_sessions or self.user_sessions[username].closed:
            logger.debug(f"Creating new aiohttp ClientSession for user {username} with cookie support")
            # Create session with automatic cookie handling
            self.user_sessions[username] = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
        else:
            logger.debug(f"Reusing existing aiohttp ClientSession for user {username}")
        return self.user_sessions[username]

    async def close_all_sessions(self):
        """Close all user sessions and free associated resources.

        Closes all active aiohttp ClientSessions managed by this manager
        to ensure proper cleanup of network resources.
        """
        logger.info("Closing all user sessions")
        for username, session in self.user_sessions.items():
            if session and not session.closed:
                logger.debug(f"Closing aiohttp ClientSession for user {username}")
                await session.close()


# Global user session manager instance
user_session_manager = UserSessionManager()

class HipoData(dict):
    """A specialized dictionary for storing structured medical data with section support.
    
    This class extends the standard dict to provide a convenient store() method
    for organizing parsed medical data in hierarchical sections. It's particularly 
    useful for parsing structured HTML data from medical records where information 
    needs to be grouped by logical categories.
    
    The store() method handles data storage with the following rules:
    1. If section is None: Store key-value directly in root dictionary
    2. If section is provided but key is None: Store value with section name as key in root
    3. If both section and key are provided: Store value in nested section[key] structure
    
    Automatic data processing:
    - Lists with single elements are automatically unwrapped
    - String values are stripped of leading/trailing whitespace
    - Sections are created automatically when first referenced
    
    Examples:
        data = HipoData()
        
        # Store in root (section=None)
        data.store(None, "name", "John Doe")  # {"name": "John Doe"}
        
        # Store in a section
        data.store("patient", "id", "12345")  # {"patient": {"id": "12345"}}
        
        # Store with section as key (key=None)
        data.store("diagnosis", None, "Healthy")  # {"diagnosis": "Healthy"}
    """
    
    def __init__(self, **kwargs):
        """Initialize HipoData with optional key/value pairs.
        
        Args:
            **kwargs: Key/value pairs to initialize the dictionary with
        """
        super().__init__(**kwargs)
    
    def set_error(self, message: str) -> None:
        """Set the status to 'error' and the message to the provided error message.
        
        Args:
            message: Error message to set
        """
        self["status"] = "error"
        self["message"] = message
    
    def set_success(self) -> None:
        """Set the status to 'success' and clear any error message."""
        self["status"] = "success"
        self["message"] = ""
    
    def store(self, key: str, value: str = None) -> None:
        """Store a value in the dictionary with automatic data processing.
        
        Args:
            key: Key for the value. Can be in format "section.key" for nested storage.
            value: Value to store. Lists with one element are automatically unwrapped,
                  and string values are stripped of whitespace.
                  
        Storage logic:
        - If key is in format "section.key": Store value in nested section[key] structure
        - Otherwise: Store key-value pair directly in root dict
        - Sections are created automatically if they don't exist
        """
        # Check if key has dot notation for nested storage
        if '.' in key:
            section, sub_key = key.split('.', 1)
            
            # Create section if it doesn't exist
            if section not in self:
                self[section] = {}
            
            # Ensure section is a dict
            if not isinstance(self[section], dict):
                # Convert existing value to dict
                self[section] = {"": self[section]}
            
            data = self[section]
            
            # Auto-unwrap single element lists
            if isinstance(value, list) and len(value) == 1:
                value = value[0]
            # Auto-strip string values
            if isinstance(value, str):
                value = value.strip()
                
            data[sub_key] = value
        else:
            # Store directly in root
            # Auto-unwrap single element lists
            if isinstance(value, list) and len(value) == 1:
                value = value[0]
            # Auto-strip string values
            if isinstance(value, str):
                value = value.strip()
            self[key] = value
    
    def store_list(self, key: str, value: str = None) -> None:
        """Store a value in the dictionary with automatic data processing.
        
        Args:
            key: Key for the value. Can be in format "section.key" for nested storage.
            value: Value to store. Lists are preserved as lists.
                  
        Storage logic:
        - If key is in format "section.key": Store value in nested section[key] structure
        - Otherwise: Store key-value pair directly in root dict
        - Sections are created automatically if they don't exist
        """
        # Check if key has dot notation for nested storage
        if '.' in key:
            section, sub_key = key.split('.', 1)
            
            # Create section if it doesn't exist
            if section not in self:
                self[section] = {}
            
            # Ensure section is a dict
            if not isinstance(self[section], dict):
                # Convert existing value to dict
                self[section] = {"": self[section]}
            
            data = self[section]
            
            # Auto-unwrap single element lists
            if not isinstance(value, list):
                value = list(value)
                
            data[sub_key] = value
        else:
            # Store directly in root
            # Auto-unwrap single element lists
            if not isinstance(value, list):
                value = list(value)
            self[key] = value

    def get_section_key(self, section_key_str: str) -> tuple:
        """Parse a string in format 'section.key' and return as tuple.
        
        Args:
            section_key_str: String in format 'section.key'
            
        Returns:
            Tuple of (section, key)
        """
        if '.' in section_key_str:
            parts = section_key_str.split('.', 1)
            return (parts[0].strip(), parts[1].strip())
        else:
            return (section_key_str.strip(), None)

    def get(self, section_key_str: str, default: Any = "") -> Any:
        """Get value from self[section][key] using 'section.key' string format.
        
        Args:
            section_key_str: String in format 'section.key'
            default: Default value to return if key is not found (default: empty string)
            
        Returns:
            Value at self[section][key] if it exists, otherwise default value
        """
        section, key = self.get_section_key(section_key_str)
        
        # Handle case where key is None
        if key is None:
            # Check if section exists in root
            if section in self:
                return self[section]
            return default
        
        # Check if section exists and is a dict
        if section in self and isinstance(self[section], dict):
            # Check if key exists in section
            if key in self[section]:
                return self[section][key]
        return default

    def set(self, section_key_str: str, value: Any) -> None:
        """Set value to self[section][key] using 'section.key' string format.
        
        Args:
            section_key_str: String in format 'section.key'
            value: Value to set
        """
        section, key = self.get_section_key(section_key_str)
        
        # Handle case where key is None
        if key is None:
            # Store value directly in root with section as key
            self[section] = value
            return
        
        # Create section if it doesn't exist
        if section not in self:
            self[section] = {}
        
        # Set the value in section[key]
        self[section][key] = value


class HipoClient:
    """Base client for interacting with the Hipocrate medical system.

    Provides core functionality for authenticating with the Hipocrate service,
    making HTTP requests, handling sessions, caching responses, and parsing
    medical data from HTML content. This class should be extended for specific
    use cases rather than used directly.
    """

    def __init__(self, service_url: str, request=None):
        """Initialize the Hipocrate client.

        Args:
            service_url: Base URL of the Hipocrate service
            request: Optional request object to extract credentials from
        """
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
        if request and hasattr(request, 'auth_credentials'):
            self.username, self.password = request.auth_credentials

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

    async def login_if_needed(self, session, username: str, password: str) -> bool:
        """Attempt to login to the Hipocrate service if needed.

        Checks if we're currently on the login page, and if so, performs login
        using the provided credentials. Handles the complete login flow including
        initial cookie setup and form submission.

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
                return error_div.get_text().strip()
            return ""
        except Exception as e:
            logger.error(f"Error extracting error message: {e}")
            return ""

    async def post_form(self, url, data=None):
        """Submit a form to the Hipocrate service, following redirects.

        This method handles the common pattern of making authenticated POST requests
        with proper form data submission and redirect following.

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
        """Retrieve a page from the Hipocrate service, following redirects.

        This method handles the common pattern of making authenticated requests with
        redirect following, which can be reused by derived classes. Implements
        caching and automatic authentication handling.

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

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        """Parse HTML content and extract structured data.

        Abstract method to be implemented by subclasses for specific data parsing.

        Args:
            html_content: HTML content to parse
            **kwargs: Additional arguments for parsing

        Returns:
            HipoData containing parsed data
        """
        data = HipoData(status = "success", message = "")
        return data

    def fhir_response(self, parsed_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Convert parsed data to FHIR-compatible format.

        Abstract method to be implemented by subclasses for FHIR conversion.

        Args:
            parsed_data: Parsed data from parse_data method
            **kwargs: Additional arguments for FHIR conversion

        Returns:
            Dictionary containing FHIR-compatible data
        """
        return {}

    async def fetch_and_parse(self, *args, max_redirects=5, **kwargs):
        """Generic method to fetch data from an endpoint and parse it.

        This method provides a reusable way to fetch data from any endpoint and parse it
        using the instance parser method. Handles authentication, caching, and error handling.

        Args:
            max_redirects: Maximum number of redirects to follow (default: 5)
            **kwargs: Arguments for URL formatting and parsing

        Returns:
            HipoData containing parsed data or error information
        """
        # Create the data object
        data = HipoData(status="success", message="")
        # Create the specific request url
        url = self.request_url.format(**kwargs)
        try:
            # Retrieve the page
            response_text, success, error_response = await self.get_page(url, max_redirects)

            # Check for errors in the response
            if not success:
                data.set_error(error_response)
                return data

            # Parse the data using the parser function
            parsed_data = self.parse_data(response_text, **kwargs)
            return parsed_data

        except Exception as e:
            data.set_error("Data retrieval failed")
            return data

    async def fetch_repond_fhir(self, *args, max_redirects=5, **kwargs):
        """Generic method to fetch data from an endpoint and convert it to FHIR format.

        This method provides a reusable way to fetch data from any endpoint, parse it,
        and convert it to FHIR-compatible format using the instance parser and FHIR methods.

        Args:
            max_redirects: Maximum number of redirects to follow (default: 5)
            **kwargs: Arguments for URL formatting and parsing

        Returns:
            Tuple of (fhir_data, error_response) where one will be None
        """

        try:
            # Retrieve and parse the page
            parsed_data = await self.fetch_and_parse(**kwargs)

            # Check for errors in the response
            if parsed_data.get("status") == "error":
                return parsed_data

            # Convert parsed data to FHIR resource
            parsed_data['fhir'] = self.fhir_response(parsed_data, **kwargs)
            return parsed_data

        except Exception as e:
            data = {"status": "error", "message": "Data retrieval failed", "exception": str(e)}
            logger.error(data["message"])
            return data

    async def debug_page(self, *args, max_redirects=5, **kwargs):
        """Generic method to fetch data from an endpoint and return raw HTML.

        This method provides a reusable way to fetch raw HTML content from any endpoint
        without parsing it. Useful for debugging purposes.

        Args:
            max_redirects: Maximum number of redirects to follow (default: 5)
            **kwargs: Arguments for URL formatting

        Returns:
            String containing raw HTML content or error information
        """
        # Create the specific request url
        url = self.request_url.format(**kwargs)
        try:
            # Retrieve the page
            response_text, success, error_response = await self.get_page(url, max_redirects)

            # Check for errors in the response
            if not success:
                return f"Error: {error_response}"

            # Return the raw HTML content
            return response_text

        except Exception as e:
            return f"Error: Data retrieval failed - {str(e)}"



class HipoClientPatient(HipoClient):
    """Specialized client for patient related operations in the Hipocrate medical system.

    Handles retrieval and parsing of patient information including personal data,
    contact information, medical identifiers, and related encounter IDs.
    """

    def __init__(self, service_url: Optional[str] = None, request: Optional[web.Request] = None):
        """Initialize the patient client.

        Args:
            service_url: Base URL of the Hipocrate service
            request: Optional request object to extract credentials from
        """
        # Initialize the parent
        super().__init__(service_url = service_url, request = request)
        # The request endpoint
        self.request_url = "/Pacient/edit.asp?id={id}"

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        """Parse HTML patient content and extract structured data.

        Extracts patient information from patient HTML content,
        including personal data, contact information, medical identifiers,
        and related encounter IDs.

        Args:
            html_content: HTML content of the patient page
            **kwargs: Additional arguments

        Returns:
            HipoData containing parsed patient data organized in sections:
            - patient: Patient information (name, id, cnp, etc.)
            - presentation: List of presentation IDs
            - checkin: List of admission/checkin IDs
            - checkout: List of discharge/checkout IDs
        """
        # Initialize result dictionary
        data = HipoData(status="success", message="", patient = {})

        try:
            # Parse HTML content
            soup = BeautifulSoup(html_content, 'html.parser')

            # Check if this is a single patient page by looking for 'Date pasaportale' in title
            if not self.is_expected_page(soup, 'Date pasaportale'):
                # Log snippet of response for debugging
                data.set_error(f"Unexpected page for Patient: {self.get_title(soup)}")
                logger.warning(f"{data['message']}: {self.get_error(soup)}")
                return data

            # Check if there is patient data on page by getting the name from the div with id "div_navbar"
            patient_name_from_navbar = extract_text_from_element(soup, id='div_navbar')
            if not patient_name_from_navbar:
                data.set_error("Patient name from navbar is empty, invalid patient id")
                return data

            # Extract patient name
            data.store("patient.name", patient_name_from_navbar)

            # Extract patient name from input elements
            data.store("patient.family_name", extract_value_from_input(soup, id="strNume"))
            data.store("patient.given_name", extract_value_from_input(soup, id="strPrenume"))
            if data.get("patient.family_name") and data.get("patient.given_name"):
                data.store("patient.name", f"{data.get('patient.family_name')} {data.get('patient.given_name')}")


            # Extract patient CNP from input element with id "strCNP"
            data.store("patient.cnp", extract_value_from_input(soup, id="strCNP"))

            # Extract patient id from hidden input with id "hdnCodeID"
            data.store("patient.id", extract_value_from_input(soup, id="hdnCodeID"))

            # Extract CID
            data.store("patient.cid", extract_value_from_input(soup, id="strCID"))

            # Extract phone
            data.store("patient.phone", extract_value_from_input(soup, id="strTelefon"))

            # Extract email
            data.store("patient.email", extract_value_from_input(soup, id="strEmail"))

            # Extract weight
            data.store("patient.weight", extract_value_from_input(soup, id="strGreutate"))

            # Extract height
            data.store("patient.height", extract_value_from_input(soup, id="strInaltime"))

            # Extract MCP
            data.store("patient.mcp", extract_value_from_input(soup, id="strmcp"))

            # Extract address from SELECT with id strDomLegal_LocId
            data.store("patient.address", extract_selected_from_dropdown(soup, id='strDomLegal_LocId'))

            # Derive sex and birth date from CNP if available
            if data.get("patient.cnp"):
                parsed_cnp = parse_cnp(data.get("patient.cnp"))
                if parsed_cnp.get("valid"):
                    data.store("patient.sex", parsed_cnp.get("gender", "unknown"))
                    data.store("patient.birth_date", parsed_cnp.get("birth_date", ""))

            # If we couldn't derive birth date from CNP, try to get it from strDataNastere input
            if not data.get("patient.birth_date"):
                birth_date = extract_value_from_input(soup, id='strDataNastere')
                if birth_date and re.match(r'\d{2}/\d{2}/\d{4}', birth_date):
                    # Convert DD/MM/YYYY format to YYYY-MM-DD
                    try:
                        day, month, year = birth_date.split('/')
                        data.store("patient.birth_date", f"{year}-{month}-{day}")
                    except Exception:
                        pass  # Keep birth_date empty if parsing fails

            # Extract encounters / presentations
            data.store_list("presentation", extract_ids_from_links(soup, r'../files/presentation\.asp\?id=(\d+)'))

            # Extract admissions / checkins
            data.store_list("checkin", extract_ids_from_links(soup, r'../files/checkin\.asp\?id=(\d+)'))

            # Extract discharges / checkouts
            data.store_list("checkout", extract_ids_from_links(soup, r'../files/checkout\.asp\?id=(\d+)'))
            
            # Return the data
            return data
        
        except Exception as e:
            logger.error(f"Error parsing patient data: {e}")
            data.set_error(str(e))
            return data

    def fhir_response(self, parsed_data: HipoData[str, Any], **kwargs) -> Dict[str, Any]:
        """Convert parsed patient data to FHIR Patient resource.

        Transforms parsed patient data into a FHIR-compatible Patient
        resource with proper structure, references, coding systems, and extensions.

        Args:
            parsed_data: Parsed patient data from parse_data method
            **kwargs: Additional arguments including 'http_request' for host information
                     and 'id' for patient ID

        Returns:
            FHIR Patient resource as dictionary
        """
        # Extract http_request from kwargs if available, otherwise use self.request
        http_request = kwargs.get('http_request', self.request)
        
        # Get patient ID from the request URL parameters
        patient_id = kwargs.get('id', '')
        
        try:
            # Use already extracted family name and given name if available
            family_name = parsed_data.get("patient.family_name", "")
            given_names = [parsed_data.get("patient.given_name", "")] if parsed_data.get("patient.given_name") else []

            # Fallback to parsing from full name if family/given names are not available
            if not family_name and not given_names:
                name_parts = parsed_data.get("patient.name", "").split()
                family_name = name_parts[0] if len(name_parts) > 0 else ""
                given_names = name_parts[1:] if len(name_parts) > 1 else []

            # Use already extracted gender and birth date if available
            gender = parsed_data.get("patient.sex", "")
            birth_date = parsed_data.get("patient.birth_date", "")

            # Create FHIR Patient resource using the FHIR class
            fhir_patient = FHIRPatient(
                id=parsed_data.get("patient.id", patient_id),
                active=True,
            )
            if gender:
                fhir_patient["gender"] = gender
            if birth_date:
                fhir_patient["birthDate"] = birth_date

            # Add name
            name = {
                "use": "official",
                "family": family_name,
                "given": given_names
            }
            fhir_patient["name"] = [name]

            # Add telecom information if available
            telecom = []
            if parsed_data.get("patient.phone", None):
                telecom.append({
                    "system": "phone",
                    "value": parsed_data.get("patient.phone")
                })

            if parsed_data.get("patient.email", None):
                telecom.append({
                    "system": "email",
                    "value": parsed_data.get("patient.email")
                })

            if telecom:
                fhir_patient["telecom"] = telecom

            # Add address information if available
            address = []
            if parsed_data.get("patient.address", None):
                address.append({
                    "text": parsed_data.get("patient.address")
                })

            if address:
                fhir_patient["address"] = address

            # Add extensions for additional patient data
            extensions = []

            # Add weight if available
            if parsed_data.get("patient.weight", None):
                extensions.append({
                    "url": "http://hl7.org/fhir/us/vitals/StructureDefinition/body-weight",
                    "valueString": parsed_data.get("patient.weight")
                })

            # Add height if available
            if parsed_data.get("patient.height", None):
                extensions.append({
                    "url": "http://hl7.org/fhir/us/vitals/StructureDefinition/height",
                    "valueString": parsed_data.get("patient.height")
                })

            # Add extensions for encounter/admission/discharge IDs
            presentations = parsed_data.get("patient.presentation", [])
            if presentations and http_request:
                extensions.append({
                    "url": f"{http_request.scheme}://{http_request.host}/fhir/StructureDefinition/presentation-ids",
                    "valueString": ",".join(presentations) if isinstance(presentations, list) else str(presentations)
                })
                
            checkins = parsed_data.get("patient.checkin", [])
            if checkins and http_request:
                extensions.append({
                    "url": f"{http_request.scheme}://{http_request.host}/fhir/StructureDefinition/checkin-ids",
                    "valueString": ",".join(checkins) if isinstance(checkins, list) else str(checkins)
                })
                
            checkouts = parsed_data.get("patient.checkout", [])
            if checkouts and http_request:
                extensions.append({
                    "url": f"{http_request.scheme}://{http_request.host}/fhir/StructureDefinition/checkout-ids",
                    "valueString": ",".join(checkouts) if isinstance(checkouts, list) else str(checkouts)
                })

            if extensions:
                fhir_patient["extension"] = extensions

            # Add identifiers
            identifiers = []

            # Add CNP as identifier if available
            if parsed_data.get("patient.cnp", None) and http_request:
                identifiers.append({
                    "use": "official",
                    "system": f"{http_request.scheme}://{http_request.host}/fhir/NamingSystem/patient-cnp",
                    "value": parsed_data.get("patient.cnp")
                })

            # Add CID if available
            if parsed_data.get("patient.cid", None) and http_request:
                identifiers.append({
                    "system": f"{http_request.scheme}://{http_request.host}/fhir/NamingSystem/patient-cid",
                    "value": parsed_data.get("patient.cid")
                })

            # Add MCP if available
            if parsed_data.get("patient.mcp", None) and http_request:
                identifiers.append({
                    "system": f"{http_request.scheme}://{http_request.host}/fhir/NamingSystem/patient-mcp",
                    "value": parsed_data.get("patient.mcp")
                })

            if identifiers:
                fhir_patient["identifier"] = identifiers

            # Return the FHIR Patient resource as dict
            return fhir_patient.to_dict()

        except Exception as e:
            logger.error(f"Error converting patient data to FHIR: {e}")
            return {}


class HipoClientPatientSearch(HipoClientPatient):
    """Specialized client for patient search operations in the Hipocrate medical system.

    Handles searching for patients by various criteria including name, CNP (personal identification number),
    partial CNP, and patient code. Supports both single patient and multiple patient result parsing.
    """

    def __init__(self, service_url: Optional[str] = None, request: Optional[web.Request] = None):
        """Initialize the patient search client.

        Args:
            service_url: Base URL of the Hipocrate service
            request: Optional request object to extract credentials from
        """
        # Initialize the parent
        super().__init__(service_url = service_url, request = request)
        # The request endpoint
        self.request_url = "/files/search.asp?what=PA"

    async def search(self, search_term, **kwargs):
        """Search for patients by various criteria.

        Handles searching for patients by name, CNP, partial CNP, or patient code.
        Automatically determines the search type based on the input format.

        Args:
            search_term: Search term - can be name, CNP, partial CNP (ending with *), or patient code
            **kwargs: Additional arguments

        Returns:
            HipoData containing search results or error information
        """
        # Initialize result data
        data = HipoData(status="success", message="", patients=[])

        # Determine search type based on input
        search_type = "name"  # default

        # Check if search term is numeric
        if search_term.isdigit():
            # If it's 13 digits, validate as CNP
            if len(search_term) == 13:
                if parse_cnp(search_term).get("valid", False):
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

        try:
            # Post the request
            response_text, success, error_response = await self.post_form(self.request_url, search_data)

            # Check for errors in the response
            if not success:
                data.set_error(error_response.get("message", "Unknown error during search"))
                return data

            # Parse the data using the patient parser function, for a single patient
            parsed_data = self.parse_one_patient_data(response_text, **kwargs)
            if parsed_data and parsed_data.get("status") == "success":
                return parsed_data
            
            # Try to parse as multiple patients page
            parsed_data = self.parse_multiple_patients_data(response_text, **kwargs)
            if parsed_data and parsed_data.get("status") == "success":
                return parsed_data
            
            data.set_error("Patient not found")
            return data

        except Exception as e:
            data.set_error(f"Patient search failed: {str(e)}")
            return data

    def parse_one_patient_data(self, html_content: str, **kwargs) -> HipoData:
        """Parse HTML content for a single patient page.

        Args:
            html_content: HTML content of the patient page
            **kwargs: Additional arguments

        Returns:
            HipoData containing parsed patient data
        """
        return self.parse_data(html_content, **kwargs)

    def parse_multiple_patients_data(self, html_content: str) -> HipoData:
        """Parse HTML content for multiple patient search results and extract patient data.

        Extracts patient names, CNP, and ids from search results page with multiple patients.

        Args:
            html_content: HTML content of the search results page

        Returns:
            HipoData containing patient search results
        """
        # Initialize empty dict for patients
        data = HipoData(status="success", message="", patients = {})

        try:
            # Parse HTML content with BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')

            # Check if this is a search results page by looking for 'Fisier' in title
            if not self.is_expected_page(soup, 'Fisier'):
                # Return empty list if not expected page
                data.set_error(f"Unexpected page for PatientSearch: {self.get_title(soup)}")
                logger.warning(f"{data['message']}: {self.get_error(soup)}")
                return data

            # Find all links with the pattern javascript:Edit('patient_id')
            pattern = r"javascript:Edit\('([^']+)'\);"
            data["patients"] = extract_text_ids_from_links(soup, pattern)

        except Exception as e:
            logger.error(f"Error parsing multiple patients data: {e}")
            data.set_error(str(e))

        # Return the patients dict
        return data


class HipoClientServiceRequest(HipoClient):
    """Specialized client for service request related operations in the Hipocrate medical system.

    Handles retrieval and parsing of medical service requests including laboratory
    orders, imaging requests, and other medical service requisitions.
    """

    def __init__(self, service_url: Optional[str] = None, request: Optional[web.Request] = None):
        """Initialize the service request client.

        Args:
            service_url: Base URL of the Hipocrate service
            request: Optional request object to extract credentials from
        """
        # Initialize the parent
        super().__init__(service_url = service_url, request = request)
        # The request endpoint
        self.request_url = "/Analyse/LabRequest/buletinRecoltari.asp?id={id}"

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        """Parse HTML service request content and extract structured data.

        Extracts patient information and medical data from service request HTML content,
        including medic information, diagnosis, imaging studies, and request details.

        Args:
            html_content: HTML content of the service request page
            **kwargs: Additional arguments

        Returns:
            HipoData containing parsed service request data organized in sections:
            - patient: Patient information (name, id)
            - checkin: Admission information (medic, id, diagnosis)
            - request: Request information (clinical_comments, lab_comments, datetime, is_urgent)
            - studies: List of requested imaging studies
        """
        # Initialize result dictionary
        data = HipoData(status="success", message="")

        try:
            # Parse HTML content
            soup = BeautifulSoup(html_content, 'html.parser')

            # Extract patient name
            data.store("patient.name", extract_text_after_label(soup, r'Nume Pacient:'))

            # Extract patient ID
            patient_link = soup.find('a', href=re.compile(r'../Pacient/edit\.asp\?id='))
            if patient_link:
                data.store("patient.id", extract_id_from_link(patient_link))
            #else:
            #    data.set_error("Could not extract patient ID from service request")
            #    return data

            # Extract medic
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

            # Extract request datetime (Data si ora cererii)
            data.store("request.datetime", extract_text_after_label(soup, r'Data si ora cererii:', stop_at=r'Receptionat'))

            # Extract request urgency
            data.store("request.is_urgent", "~URGENTA~" in html_content)

            # Return the data
            return data
        
        except Exception as e:
            logger.error(f"Error parsing service request data: {e}")
            data.set_error(str(e))
            return data

    def fhir_response(self, parsed_data: HipoData[str, Any], **kwargs) -> Dict[str, Any]:
        """Convert parsed service request data to FHIR ServiceRequest resource.

        Transforms parsed service request data into a FHIR-compatible ServiceRequest
        resource with proper structure, references, coding systems, and extensions.

        Args:
            parsed_data: Parsed service request data from parse_data method
            **kwargs: Additional arguments including 'http_request' for host information
                     and 'id' for service request ID

        Returns:
            FHIR ServiceRequest resource as dictionary
        """
        # Extract http_request from kwargs if available
        http_request = kwargs.get('http_request')
        
        # Get service request ID from the request URL parameters
        service_request_id = kwargs.get('id', '')
        
        try:
            # Create FHIR ServiceRequest resource using the FHIR class
            fhir_service_request = FHIRServiceRequest(
                id=service_request_id,
                status="active",
                intent="order",
                priority="urgent" if parsed_data.get("request.is_urgent", False) else "routine"
            )

            # Create subject reference
            patient_id = parsed_data.get("patient.id")
            subject = Reference(
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
                
            code = CodeableConcept(
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
                fhir_service_request["requester"] = Reference(display=medic)

            # Add encounter if we can derive it
            admission_id = parsed_data.get("checkin.id")
            if admission_id:
                # Handle case where admission_id might be a list
                if isinstance(admission_id, list) and len(admission_id) > 0:
                    admission_id = admission_id[0]
                fhir_service_request["encounter"] = Reference(
                    reference=f"Encounter/{admission_id}"
                )

            # Add reason code if diagnosis is available
            diagnosis = parsed_data.get("checkin.diagnosis")
            if diagnosis:
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
                    order_detail = CodeableConcept(
                        coding=[{
                            "system": study_system_url,
                            "code": f"study-{code}",
                            "display": description
                        }],
                        text=description
                    )
                    order_details.append(order_detail)
                fhir_service_request["orderDetail"] = order_details

            # Add authoredOn if request datetime is available
            request_datetime = parsed_data.get("request.datetime")
            if request_datetime:
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



class HipoClientImagingStudy(HipoClient):
    """Specialized client for imaging study related operations in the Hipocrate medical system.

    Handles retrieval and parsing of medical imaging studies including radiology,
    ultrasound, CT, and MRI examination requests and results.
    """

    def __init__(self, service_url: Optional[str] = None, request: Optional[web.Request] = None):
        """Initialize the service request client.

        Args:
            service_url: Base URL of the Hipocrate service
            request: Optional request object to extract credentials from
        """
        # Initialize the parent
        super().__init__(service_url = service_url, request = request)
        # The request endpoint
        self.request_url = "/Analyse/LabRequest/edit.asp?id={id}"

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        """Parse HTML service request content and extract structured data.

        Extracts patient information and medical data from service request HTML content,
        including medic information, diagnosis, imaging studies, and request details.

        Args:
            html_content: HTML content of the service request page
            **kwargs: Additional arguments

        Returns:
            HipoData containing parsed service request data organized in sections:
            - patient: Patient information (name, id)
            - checkin: Admission information (medic, id, diagnosis)
            - request: Request information (clinical_comments, lab_comments, datetime, is_urgent)
            - studies: List of requested imaging studies
        """
        # Initialize result dictionary
        data = HipoData(status="success", message="")

        try:
            # Parse HTML content with BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')

            # Check if this is a diagnostic request/report page
            if not self.is_expected_page(soup, 'Cerere de investigatii paraclinice'):
                # Log snippet of response for debugging
                data.set_error(f"Unexpected page for ImagingStudy: {self.get_title(soup)}")
                logger.warning(f"{data['message']}: {self.get_error(soup)}")
                return data

            # Extract patient name from the table with patient data
            data.store("patient.name", extract_text_after_label(soup, r'Nume:', 'tr', stop_at=r'\['))

            # Extract patient CNP from the table with patient data
            patient_cnp = extract_value_from_input(soup, id="strCNP")
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

            # Extract medic
            data.store("checkin.medic", extract_text_after_label(soup, r'Medic:', 'tr'))

            # Extract the clinical comments
            data.store("checkin.diagnosis", extract_text_after_label(soup, r'prezumtiv:', 'tr'))

            # Extract the clinical comments
            data.store("request.clinical_comments", extract_text_after_label(soup, r'Informatii suplimentare:', 'tr', stop_at=r'Motiv'))

            # Extract the lab comments
            data.store("request.lab_comments", extract_text_from_element(soup, id="strComments"))

            # Extract the justification
            data.store("request.justification", extract_text_from_element(soup, id="strJustificare"))

            # Extract ICD10 coded diagnosis
            data.store("request.icd10", extract_text_after_label(soup, r'Diagnostic:', 'tr'))

            # Extract requester and request date and time
            req = extract_text_after_label(soup, r'Ceruta:', 'tr')
            if req and '-' in req:
                try:
                    request_medic, request_datetime = req.split('-', 1)
                    data.store("request.medic", request_medic)
                    # Try to parse the datetime
                    dt = parse_date_time(request_datetime)
                    if dt:
                        data.store("request.datetime", dt.isoformat())
                    else:
                        # If parsing fails, keep the original string
                        data.store("request.datetime", request_datetime.strip())
                except ValueError:
                    # Handle case where split doesn't work as expected
                    data.store("request.info", req)

            # Extract performer (validator) from the domain section
            validator = extract_text_after_label(soup, r'Validat de:', 'td', stop_at=r'Data')
            if validator:
                data.store("validation.validator", validator)

            # Extract validation datetime
            validation_datetime = extract_value_from_input(soup, id="dataefectuarii")
            if validation_datetime:
                # Try to parse the datetime
                dt = parse_date_time(validation_datetime)
                if dt:
                    data.store("validation.datetime", dt.isoformat())
                else:
                    # If parsing fails, keep the original string
                    data.store("validation.datetime", validation_datetime)
            
            # For each strAnalyseExec input, find the parent 'td' and extract examination name from first 'b' element
            studies = []
            for input_elem in soup.find_all('input', {'name': 'strAnalyseExec'}):
                parent_td = input_elem.find_parent('td')
                if parent_td:
                    first_b = parent_td.find('b')
                    if first_b:
                        study_title = first_b.get_text(strip=True)
                    else:
                        study_title = parent_td.get_text(strip=True)
                    # Find the 'table' parent and then the 'center' sibling
                    parent_table = parent_td.find_parent('table')
                    container = parent_table.find_next_sibling('center')
                    study_result = None
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
            data.store_list("studies", studies)

            # Store urgency flag
            data.store("request.is_urgent", "~URGENTA~" in html_content)

            # Return the parsed report data
            return data

        except Exception as e:
            logger.error(f"Error parsing report data: {e}")
            return HipoData(status="success", message=f"{e}")

    def fhir_response(self, parsed_data: HipoData[str, Any], **kwargs) -> Dict[str, Any]:
        """Convert parsed imaging study data to FHIR ImagingStudy resource.

        Transforms parsed imaging study data into a FHIR-compatible ImagingStudy
        resource with proper structure, references, coding systems, and extensions.

        Args:
            parsed_data: Parsed imaging study data from parse_data method
            **kwargs: Additional arguments including 'http_request' for host information
                     and 'id' for study ID

        Returns:
            FHIR ImagingStudy resource as dictionary
        """
        # Extract http_request from kwargs if available
        http_request = kwargs.get('http_request')
        
        # Get study ID from the request URL parameters
        study_id = kwargs.get('id', '')
        
        try:
            # Create FHIR ImagingStudy resource
            fhir_imaging_study = {
                "resourceType": "ImagingStudy",
                "id": study_id,
                "status": "available",
                "subject": {
                    "reference": f"Patient/{parsed_data.get('patient.id', '')}"
                },
                "basedOn": {
                    "reference": f"ServiceRequest/{study_id}"
                },
                "started": parsed_data.get("request.datetime", datetime.now().isoformat()),
                "series": []
            }

            # Add modality if available in studies
            studies = parsed_data.get("studies", [])
            if studies and len(studies) > 0 and isinstance(studies[0], dict):
                first_study = studies[0]
                study_type = first_study.get("type", "").upper()
                if study_type:
                    # Map study types to DICOM modality codes
                    modality_mapping = {
                        "radio": "CR",  # Computed Radiography
                        "eco": "US",    # Ultrasound
                        "ct": "CT",     # Computed Tomography
                        "mri": "MR",    # Magnetic Resonance
                    }
                    modality_code = modality_mapping.get(study_type, "OT")  # Other
                    fhir_imaging_study["modality"] = {
                        "system": "http://dicom.nema.org/resources/ontology/DCM",
                        "code": modality_code,
                        "display": modality_code
                    }

            # Add patient information if available
            if parsed_data.get("patient.name"):
                fhir_imaging_study["identifier"] = [{
                    "system": f"{http_request.scheme}://{http_request.host}/fhir/NamingSystem/patient-name" if http_request else "http://example.com/fhir/NamingSystem/patient-name",
                    "value": parsed_data.get("patient.name")
                }]

            if parsed_data.get("patient.cnp"):
                if "identifier" not in fhir_imaging_study:
                    fhir_imaging_study["identifier"] = []
                fhir_imaging_study["identifier"].append({
                    "system": f"{http_request.scheme}://{http_request.host}/fhir/NamingSystem/patient-cnp" if http_request else "http://example.com/fhir/NamingSystem/patient-cnp",
                    "value": parsed_data.get("patient.cnp")
                })

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
                        "description": study.get("title", "Imaging Study"),
                        "started": parsed_data.get("request.datetime", datetime.now().isoformat()),
                        "instance": []
                    }
                    
                    # Use the study modality for the series if available
                    study_type = study.get("type", "").upper()
                    if study_type:
                        modality_mapping = {
                            "radio": "CR",  # Computed Radiography
                            "eco": "US",    # Ultrasound
                            "ct": "CT",     # Computed Tomography
                            "mri": "MR",    # Magnetic Resonance
                        }
                        series_modality = modality_mapping.get(study_type.lower(), "OT")
                        series["modality"] = {
                            "system": "http://dicom.nema.org/resources/ontology/DCM",
                            "code": series_modality,
                            "display": series_modality
                        }
                        
                    # Add the instance
                    fhir_imaging_study["series"].append(series)

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
            return {}


class HipoClientDiagnosticReport(HipoClient):
    """Specialized client for diagnostic report related operations in the Hipocrate medical system.

    Handles retrieval and parsing of diagnostic reports including laboratory results,
    imaging study reports, and other diagnostic examination results.
    """

    def __init__(self, service_url: Optional[str] = None, request: Optional[web.Request] = None):
        """Initialize the service request client.

        Args:
            service_url: Base URL of the Hipocrate service
            request: Optional request object to extract credentials from
        """
        # Initialize the parent
        super().__init__(service_url = service_url, request = request)
        # The request endpoint
        self.request_url = "/analyse/Reports/analyseFile.asp?id={id}"

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        """Parse HTML service request content and extract structured data.

        Extracts patient information and medical data from service request HTML content,
        including medic information, diagnosis, imaging studies, and request details.

        Args:
            html_content: HTML content of the service request page
            **kwargs: Additional arguments

        Returns:
            HipoData containing parsed service request data organized in sections:
            - patient: Patient information (name, id)
            - checkin: Admission information (medic, id, diagnosis)
            - request: Request information (clinical_comments, lab_comments, datetime, is_urgent)
            - studies: List of requested imaging studies
        """
        # Initialize result dictionary
        data = HipoData(status="success", message="")

        try:
            # Parse HTML content with BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')

            # Check if this is a diagnostic request/report page
            if not self.is_expected_page(soup, 'Buletin de investigatii paraclinice'):
                # Log snippet of response for debugging
                data.set_error(f"Unexpected page for DiagnosticReport: {self.get_title(soup)}")
                logger.warning(f"{data['message']}: {self.get_error(soup)}")
                return data

            # Extract patient name from the table with patient data
            data.store("patient.name", extract_text_after_label(soup, r'PACIENT:', 'td', stop_at=r'Varsta'))

            # Extract barcode
            data.store("request.barcode", extract_text_after_label(soup, r'Nr.: '))

            # Extract medic
            data.store("checkin.medic", extract_text_after_label(soup, r'Solicitat de:', 'td'))

            # Extract the clinical comments
            data.store("checkin.diagnosis", extract_text_after_label(soup, r'DIAGNOSTIC DE TRIMITERE:', 'td'))

            # Extract medic
            data.store("request.medic", extract_text_after_label(soup, r'TRIMIS DE:\s*MEDIC', 'tr', stop_at=r'SECTIA'))

            # Extract the clinical comments
            data.store("request.clinical_comments", extract_text_after_label(soup, r'DG\.PREZUMTIV:', 'td'))

            # Extract the lab comments
            data.store("request.lab_comments", extract_text_after_label(soup, r'INDICATII SPECIALE:', 'td'))

            # Extract performer (Efectuata de catre:)
            data.store("study.performer", extract_text_after_label(soup, r'Efectuata de catre:'))

            # Extract performer (validator) from the domain section
            data.store("study.medic", extract_text_after_label(soup, r'MEDIC,|Medic validator:', 'td', stop_at=r'Semnatura'))

            # Extract study datetime
            study_datetime = extract_text_after_label(soup, r'Data investigatiei:', stop_at=r'Efectuata')
            if study_datetime:
                # Try to parse the datetime
                dt = parse_date_time(study_datetime)
                if dt:
                    data.store("study.datetime", dt.isoformat())
                else:
                    # If parsing fails, keep the original string
                    data.store("study.datetime", study_datetime)

            # Extract multiple reports: find all elements with text starting with "REZULTAT:"
            studies = []
            for result_element in soup.find_all(string=re.compile(r'^REZULTAT:', re.IGNORECASE)):
                try:
                    # The investigation name is the text after "REZULTAT:" in the element
                    element_text = result_element.get_text()
                    investigation_match = re.search(r'REZULTAT:\s*(.*?)(?:\s*$)', element_text, re.IGNORECASE)
                    study_title = ""
                    if investigation_match:
                        study_title = investigation_match.group(1).strip()

                    # Find the next div sibling which contains the actual result
                    result_div = result_element.find_next('div')
                    study_result = ""
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

                    # Add to reports list
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

            # Return the parsed report data
            return data

        except Exception as e:
            logger.error(f"Error parsing report data: {e}")
            return HipoData(status="success", message=f"{e}")

    def fhir_response(self, parsed_data: HipoData[str, Any], **kwargs) -> Dict[str, Any]:
        """Convert parsed diagnostic report data to FHIR DiagnosticReport resource.

        Transforms parsed diagnostic report data into a FHIR-compatible DiagnosticReport
        resource with proper structure, references, coding systems, and extensions.

        Args:
            parsed_data: Parsed diagnostic report data from parse_data method
            **kwargs: Additional arguments including 'http_request' for host information
                     and 'id' for report ID

        Returns:
            FHIR DiagnosticReport resource as dictionary
        """
        # Extract http_request from kwargs if available
        http_request = kwargs.get('http_request')
        
        # Get report ID from the request URL parameters
        report_id = kwargs.get('id', '')
        
        try:
            # Create FHIR DiagnosticReport resource
            fhir_report = {
                "resourceType": "DiagnosticReport",
                "id": report_id,
                "status": "final",
                "code": {
                    "coding": [
                        {
                            "system": f"{http_request.scheme}://{http_request.host}/fhir/CodeSystem/report-types" if http_request else "http://example.com/fhir/CodeSystem/report-types",
                            "code": "imaging-report",
                            "display": "Imaging Report"
                        }
                    ],
                    "text": "Diagnostic Report"
                },
                "subject": {
                    "reference": f"Patient/{parsed_data.get('patient.id', '')}"
                }
            }

            # Add basedOn reference to ServiceRequest if available
            if report_id:
                fhir_report["basedOn"] = {
                    "reference": f"ServiceRequest/{report_id}"
                }

            # Add effective date if available
            request_datetime = parsed_data.get("request.datetime")
            if request_datetime:
                fhir_report["effectiveDateTime"] = request_datetime

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

            # Add identifiers
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
            return {}


class HipoClientCheckout(HipoClient):
    """Specialized client for checkout-related operations in the Hipocrate medical system.

    Handles retrieval and parsing of patient discharge/checkout information from
    the Hipocrate system, including admission details, discharge summaries,
    diagnoses, and medic information.
    """

    def __init__(self, service_url: Optional[str] = None, request: Optional[web.Request] = None):
        """Initialize the checkout client.

        Args:
            service_url: Base URL of the Hipocrate service
            request: Optional request object to extract credentials from
        """
        # Initialize the parent
        super().__init__(service_url = service_url, request = request)
        # The request endpoint
        self.request_url = "/files/checkout.asp?id={id}"

    def parse_data(self, html_content: str, **kwargs) -> HipoData:
        """Parse HTML checkout content and extract structured data.

        Extracts patient information and medical data from checkout HTML content.
        This function parses discharge/checkout forms from the Hipocrate system
        to extract structured data about patient encounters.

        Args:
            html_content: HTML content of the checkout page
            **kwargs: Additional arguments including 'id' for checkout ID

        Returns:
            HipoData containing parsed checkout data organized in sections:
            - patient: Patient information (name, id, cnp, gender, date, age)
            - presentation: Presentation/visit information
            - checkin: Admission information (id, medic, ward, diagnosis, date, time, datetime)
            - checkout: Discharge information (date, time, datetime, epicrisis, diagnosis, 
                    medic, ward, surgery, recommendations, icd10)
        """
        # Initialize result dictionary
        data = HipoData(status="success", message="")

        try:
            # Parse HTML content with BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')

            # Check if this is the correct page by looking for title
            if not self.is_expected_page(soup, 'FISA EXTERNARE'):
                data.set_error("Page is not a discharge page")
                logger.warning("Page is not a discharge page")
                return data

            # Extract patient name and ID from the link
            patient_link = soup.find('a', href=re.compile(r'../Pacient/edit\.asp\?id='))
            if patient_link:
                data.store("patient.name", patient_link.get_text())
                # Extract patient ID from href
                data.store("patient.id", extract_id_from_link(patient_link))

            # Extract patient CNP
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

            # Extract medic
            data.store("checkin.medic", extract_text_after_label(soup, r'Medic\s*:', 'tr'))

            # Extract ward
            data.store("checkin.ward", extract_text_after_label(soup, r'Sectie\s*:', 'tr'))

            # Extract checkin diagnostic
            data.store("checkin.diagnosis", extract_text_after_label(soup, r'Diagnostic\s*:', 'tr'))

            # Extract checkin date and time from input fields
            data.store("checkin.date", extract_value_from_input(soup, id='sCIDate'))
            data.store("checkin.time", extract_value_from_input(soup, id='sCITime'))
            
            # Create combined checkin datetime
            checkin_date = data.get("checkin.date")
            checkin_time = data.get("checkin.time")
            if checkin_date and checkin_time:
                data.store("checkin.datetime", f'{checkin_date} {checkin_time}')


            # Extract checkout date and time from input fields
            data.store("checkout.date", extract_value_from_input(soup, id='sCODate'))
            data.store("checkout.time", extract_value_from_input(soup, id='sCOTime'))
            
            # Create combined checkout datetime
            checkout_date = data.get("checkout.date")
            checkout_time = data.get("checkout.time")
            if checkout_date and checkout_time:
                data.store("checkout.datetime", f'{checkout_date} {checkout_time}')

            # Extract epicrisis (textarea with id "sEpicrisysHtmlArea")
            data.store("checkout.epicrisis", extract_text_from_element(soup, 'sEpicrisys'))

            # Extract diagnostic (textarea after 'Diagnostic externare')
            data.store("checkout.diagnosis", extract_textarea_after_label(soup, r'Diagnostic externare[^:]*:'))

            # Extract medic
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

            # Return the extracted data
            return data

        except Exception as e:
            logger.error(f"Error parsing checkout data: {e}")
            data.set_error(str(e))
            return data

    def fhir_response(self, parsed_data: HipoData[str, Any], **kwargs) -> Dict[str, Any]:
        """Convert parsed checkout data to FHIR Encounter resource.

        Transforms parsed checkout data into a FHIR-compatible Encounter resource
        with proper structure, references, and coding systems.

        Args:
            parsed_data: Parsed checkout data from parse_data method
            **kwargs: Additional arguments including 'id' for encounter ID

        Returns:
            FHIR Encounter resource as dictionary
        """
        encounter_id = parsed_data.get('checkout.id', '')
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
                "reference": f"Patient/{parsed_data.get('patient.id', '')}"
            },
            "participant": []
        }

        # Add performer if available (from checkout medic)
        checkout_medic = parsed_data.get("checkout.medic")
        if checkout_medic:
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
                    "display": checkout_medic
                }
            })

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
        checkin_datetime = parsed_data.get("checkin.datetime")
        checkout_datetime = parsed_data.get("checkout.datetime")
        if checkin_datetime or checkout_datetime:
            period = {}
            if checkin_datetime:
                period["start"] = checkin_datetime
            if checkout_datetime:
                period["end"] = checkout_datetime
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
