#!/usr/bin/env python3
"""Data extraction utilities for parsing HTML content from medical records.

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

This module provides a collection of functions for extracting structured data
from HTML content, particularly focused on medical record systems. The functions
handle various data extraction scenarios including form fields, tables, links,
and specialized medical data like Romanian CNP (Personal Numerical Code).

The module is designed to work with BeautifulSoup for HTML parsing and includes
robust error handling and logging for debugging purposes.
"""

from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup, Comment
import logging
import re
from datetime import datetime

from markdown import html_to_markdown

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)8s | %(message)s'
)
logger = logging.getLogger('HipoExtractor')


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
        # First try to parse DD/MM/YYYY HH:MM:SS format
        if '/' in date_str and len(date_str) == 19:  # DD/MM/YYYY HH:MM:SS
            try:
                return datetime.strptime(date_str.strip(), '%d/%m/%Y %H:%M:%S')
            except ValueError:
                pass  # Continue to other formats
        
        # Handle common date formats like "30 Aug 2025 19:25:00"
        # Create a mapping for month abbreviations to numbers
        month_mapping: Dict[str, int] = {
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


def parse_cnp(cnp: str) -> Dict[str, Any]:
    """Parse a Romanian CNP (Personal Numerical Code) and extract meaningful data.

    Extracts gender, birth date, county, and other information from a valid CNP.
    Performs comprehensive validation including checksum verification.

    Args:
        cnp: The 13-digit Romanian CNP to parse

    Returns:
        Dictionary with parsed data including:
            - valid: bool - whether the CNP is valid
            - gender: str - "male" or "female"
            - birth_date: str - ISO format date (YYYY-MM-DD)
            - age: int - patient age in years
            - county_code: int - county code (1-52, 70-79 for diaspora, 90-99 for special)
            - county_name: str - full county name
            - serial: str - 3-digit serial number
            - control_digit: int - control digit (0-9)
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

def extract_text_after_label(soup: BeautifulSoup, label_regex: str, element_tag: str = None, stop_at: str = None) -> str:
    """Extract text content that appears after a label matching the given regex pattern.

    Searches for text matching the label pattern and extracts content that follows it
    within the same container element. Useful for extracting form field values.

    Args:
        soup: BeautifulSoup object of the parsed HTML content
        label_regex: Regular expression pattern to match label text (case insensitive)
        element_tag: HTML tag name to search within. If None, uses the parent of the label.
        stop_at: Optional regex pattern to stop extraction at (e.g., next label)

    Returns:
        Extracted field content stripped of whitespace, or empty string if not found
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
    """Extract ID from a link element's href attribute using a regex pattern.

    Args:
        link_element: BeautifulSoup element with href attribute
        id_pattern: Regex pattern to extract ID from href (default: r'id=([^&"]+)')

    Returns:
        Extracted ID string or None if not found or invalid element
    """
    # Ensure link_element is valid
    if link_element:
        href = link_element.get('href', '')
        id_match = re.search(id_pattern, href)
        if id_match:
            content = id_match.group(1)
            logger.debug(f"Extracted id for link pattern '{id_pattern}': {content}")
            return content
    return None

def extract_ids_from_links(soup: BeautifulSoup, id_pattern: str = r'id=([^&"]+)') -> List[str]:
    """Extract IDs from multiple link elements' href attributes.

    Args:
        soup: BeautifulSoup object of the parsed HTML content
        id_pattern: Regex pattern to extract ID from href (default: r'id=([^&"]+)')

    Returns:
        List of extracted ID strings (may be empty)
    """
    ids_list = []
    for item in soup.find_all('a', href=re.compile(id_pattern)):
        href = item.get('href', '')
        id_match = re.search(id_pattern, href)
        if id_match:
            ids_list.append(id_match.group(1))
    if ids_list:
        logger.debug(f"Extracted ids for link pattern '{id_pattern}': {','.join(ids_list)}")
    return ids_list

def extract_text_ids_from_links(soup: BeautifulSoup, id_pattern: str = r'id=([^&"]+)') -> dict:
    """Extract text and IDs from multiple link elements' href attributes.

    Args:
        soup: BeautifulSoup object of the parsed HTML content
        id_pattern: Regex pattern to extract ID from href (default: r'id=([^&"]+)')

    Returns:
        Dictionary mapping extracted IDs to their corresponding text content
    """
    result = {}
    for item in soup.find_all('a', href=re.compile(id_pattern)):
        href = item.get('href', '')
        id_match = re.search(id_pattern, href)
        if not id_match:
            continue
        id = id_match.group(1)
        text = item.get_text().strip().upper()
        if text == id:
            continue
        result[id] = text
    return result

def extract_value_from_input(soup: 'BeautifulSoup', element_id: str = None, name: str = None) -> str:
    """Extract the value attribute from an HTML input element by its ID or name.

    Args:
        soup: BeautifulSoup object of the parsed HTML content
        element_id: HTML input element ID to extract value from
        name: HTML input element name to extract value from

    Returns:
        Value attribute content stripped of whitespace, or empty string if not found
    """
    if not element_id and not name:
        return ""

    if name:
        input_element = soup.find('input', attrs={'name': name})
    else:
        input_element = soup.find('input', id=element_id)

    if input_element:
        identifier = name if name else element_id
        content = input_element.get('value', '').strip()
        logger.debug(f"Extracted value from '{identifier}' (by {'name' if name else 'id'}): {content}")
        return content
    return ""

def extract_text_from_element(soup: 'BeautifulSoup', element_id: str = None, name: str = None) -> str:
    """Extract text content from an HTML element by its ID or name.

    For elements with simple text content, returns the text directly.
    For complex elements with nested HTML, converts to markdown format.

    Args:
        soup: BeautifulSoup object of the parsed HTML content
        element_id: HTML element ID to extract text from
        name: HTML element name to extract text from

    Returns:
        Extracted text content or empty string if element not found or empty
    """
    if not element_id and not name:
        return ""

    element = soup.find(attrs={'name': name}) if name else soup.find(id=element_id)

    if not element:
        identifier = name if name else element_id
        logger.debug(f"Element with {'name' if name else 'id'} '{identifier}' not found")
        return ""

    identifier = name if name else element_id
    if element.string:
        content = element.string.strip()
        logger.debug(f"Extracted direct text from '{identifier}' (by {'name' if name else 'id'}): {content}")
        return content

    content = html_to_markdown(str(element))
    logger.debug(f"Extracted markdown from '{identifier}': {content[:50]}{'...' if len(content) > 50 else ''}")
    return content

def extract_selected_from_dropdown(soup: 'BeautifulSoup', element_id: str = None, name: str = None) -> str:
    """Extract the text of the selected option from a dropdown (select) element.

    Args:
        soup: BeautifulSoup object of the parsed HTML content
        element_id: HTML select element ID to extract selected option from
        name: HTML select element name to extract selected option from

    Returns:
        Text content of the selected option, or empty string if not found
    """
    if not element_id and not name:
        return ""

    element = soup.find('select', attrs={'name': name}) if name else soup.find('select', id=element_id)

    if element:
        option = element.find('option', selected=True)
        if option:
            identifier = name if name else element_id
            content = option.get_text().strip()
            logger.debug(f"Extracted text from '{identifier}' (by {'name' if name else 'id'}): {content}")
            return content
    return ""


def extract_textarea_after_label(soup: 'BeautifulSoup', label_regex: str) -> str:
    """Extract content from the first textarea that appears after a label matching the regex.

    Searches for a label matching the regex pattern and returns the content
    of the first textarea element that follows it in the DOM.

    Args:
        soup: BeautifulSoup object of the parsed HTML content
        label_regex: Regular expression pattern to match label text (case insensitive)

    Returns:
        Content of the textarea converted to markdown, or empty string if not found
    """
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
        List of rows, each row being a list of cell contents as plain text (may be empty)
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
