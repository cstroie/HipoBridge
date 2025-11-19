#!/usr/bin/env python3
"""
Extractor tests for the Hipocrate API
"""
import asyncio
import aiohttp
import os
from bs4 import BeautifulSoup
from hipp import extract_text_after_label, extract_id_from_link, extract_ids_from_links

async def test_extract_text_after_label_basic(session: aiohttp.ClientSession) -> bool:
    """Test basic functionality of extract_text_after_label function"""
    print("Testing extract_text_after_label basic functionality...")
    try:
        # Create a simple HTML test case
        html_content = """
        <html>
        <body>
            <td>Patient Name: John Doe</td>
            <td>Age: 30 years</td>
            <td>Diagnosis: Healthy</td>
        </body>
        </html>
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Test extracting patient name
        result = extract_text_after_label(soup, r'Patient Name:')
        expected = "John Doe"
        if result == expected:
            print(f"  ✓ Extracted '{result}' correctly")
            return True
        else:
            print(f"  ✗ Expected '{expected}', got '{result}'")
            return False
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False

async def test_extract_text_after_label_with_element_tag(session: aiohttp.ClientSession) -> bool:
    """Test extract_text_after_label with element_tag parameter"""
    print("Testing extract_text_after_label with element_tag...")
    try:
        # Create HTML with nested elements
        html_content = """
        <html>
        <body>
            <div>
                <td>Patient Name: John Doe</td>
            </div>
            <table>
                <tr>
                    <td>Age: 30 years</td>
                </tr>
            </table>
        </body>
        </html>
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Test extracting with td element tag
        result = extract_text_after_label(soup, r'Age:', 'td')
        expected = "30 years"
        if result == expected:
            print(f"  ✓ Extracted '{result}' correctly with element_tag")
            return True
        else:
            print(f"  ✗ Expected '{expected}', got '{result}'")
            return False
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False

async def test_extract_text_after_label_with_stop_at(session: aiohttp.ClientSession) -> bool:
    """Test extract_text_after_label with stop_at parameter"""
    print("Testing extract_text_after_label with stop_at...")
    try:
        # Create HTML with content to stop at
        html_content = """
        <html>
        <body>
            <td>Patient Name: John Doe, Age: 30, City: New York</td>
            <td>Diagnosis: Healthy - Patient is doing well</td>
        </body>
        </html>
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Test extracting with stop_at parameter
        result = extract_text_after_label(soup, r'Patient Name:', stop_at=r', City:')
        expected = "John Doe, Age: 30"
        if result == expected:
            print(f"  ✓ Extracted '{result}' correctly with stop_at")
            return True
        else:
            print(f"  ✗ Expected '{expected}', got '{result}'")
            return False
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False

async def test_extract_text_after_label_not_found(session: aiohttp.ClientSession) -> bool:
    """Test extract_text_after_label when label is not found"""
    print("Testing extract_text_after_label when label not found...")
    try:
        # Create HTML without the target label
        html_content = """
        <html>
        <body>
            <td>Patient Name: John Doe</td>
            <td>Age: 30 years</td>
        </body>
        </html>
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Test extracting non-existent label
        result = extract_text_after_label(soup, r'Diagnosis:')
        expected = ""
        if result == expected:
            print(f"  ✓ Correctly returned empty string for not found label")
            return True
        else:
            print(f"  ✗ Expected '{expected}', got '{result}'")
            return False
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False

async def test_extract_text_after_label_case_insensitive(session: aiohttp.ClientSession) -> bool:
    """Test extract_text_after_label case insensitive matching"""
    print("Testing extract_text_after_label case insensitive...")
    try:
        # Create HTML with mixed case
        html_content = """
        <html>
        <body>
            <td>PATIENT NAME: John Doe</td>
            <td>age: 30 years</td>
        </body>
        </html>
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Test case insensitive matching
        result1 = extract_text_after_label(soup, r'patient name:')
        result2 = extract_text_after_label(soup, r'AGE:')
        if result1 == "John Doe" and result2 == "30 years":
            print(f"  ✓ Case insensitive matching works correctly")
            return True
        else:
            print(f"  ✗ Case insensitive matching failed")
            return False
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False

async def test_extract_text_with_bold_tag(session: aiohttp.ClientSession) -> bool:
    """Test extract_text_after_label with bold tag format"""
    print("Testing extract_text_after_label with bold tag format...")
    try:
        # Create HTML with diagnostic in bold tag
        html_content = """
        <html>
        <body>
            <td>Diagnostic: <b>Otita supurata</b></td>
        </body>
        </html>
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Test extracting diagnostic
        result = extract_text_after_label(soup, r'Diagnostic:', 'td')
        expected = "Otita supurata"
        if result == expected:
            print(f"  ✓ Extracted '{result}' correctly from bold tag format")
            return True
        else:
            print(f"  ✗ Expected '{expected}', got '{result}'")
            return False
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False

async def test_extract_text_with_bold_and_underline_tags(session: aiohttp.ClientSession) -> bool:
    """Test extract_text_after_label with bold and underline tags"""
    print("Testing extract_text_after_label with bold and underline tags...")
    try:
        # Create HTML with diagnostic in bold and underline tags
        html_content = """
        <html>
        <body>
            <td><b>Diagnostic: </b><u>Otita supurata</u></td>
        </body>
        </html>
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Test extracting diagnostic
        result = extract_text_after_label(soup, r'Diagnostic:', 'td')
        expected = "Otita supurata"
        if result == expected:
            print(f"  ✓ Extracted '{result}' correctly from bold and underline tags")
            return True
        else:
            print(f"  ✗ Expected '{expected}', got '{result}'")
            return False
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False

async def test_extract_text_with_whitespace(session: aiohttp.ClientSession) -> bool:
    """Test extract_text_after_label with extra whitespace"""
    print("Testing extract_text_after_label with extra whitespace...")
    try:
        # Create HTML with diagnostic and extra whitespace
        html_content = """
        <html>
        <body>
            <td><b>Diagnostic: </b>   Otita supurata</td>
        </body>
        </html>
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Test extracting diagnostic
        result = extract_text_after_label(soup, r'Diagnostic:', 'td')
        expected = "Otita supurata"
        if result == expected:
            print(f"  ✓ Extracted '{result}' correctly with whitespace handling")
            return True
        else:
            print(f"  ✗ Expected '{expected}', got '{result}'")
            return False
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False

async def test_extract_id_from_link_basic(session: aiohttp.ClientSession) -> bool:
    """Test basic functionality of extract_id_from_link function"""
    print("Testing extract_id_from_link basic functionality...")
    try:
        # Create a simple HTML test case
        html_content = """
        <html>
        <body>
            <a href="edit.asp?id=12345">Link</a>
        </body>
        </html>
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        link_element = soup.find('a')
        
        # Test extracting ID from href
        result = extract_id_from_link(link_element)
        expected = "12345"
        if result == expected:
            print(f"  ✓ Extracted '{result}' correctly")
            return True
        else:
            print(f"  ✗ Expected '{expected}', got '{result}'")
            return False
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False

async def test_extract_id_from_link_with_custom_pattern(session: aiohttp.ClientSession) -> bool:
    """Test extract_id_from_link with custom pattern"""
    print("Testing extract_id_from_link with custom pattern...")
    try:
        # Create HTML with custom ID pattern
        html_content = """
        <html>
        <body>
            <a href="view.php?patient=ABC123&tab=details">Link</a>
        </body>
        </html>
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        link_element = soup.find('a')
        
        # Test extracting ID with custom pattern
        result = extract_id_from_link(link_element, r'patient=([^&"]+)')
        expected = "ABC123"
        if result == expected:
            print(f"  ✓ Extracted '{result}' correctly with custom pattern")
            return True
        else:
            print(f"  ✗ Expected '{expected}', got '{result}'")
            return False
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False

async def test_extract_id_from_link_no_href(session: aiohttp.ClientSession) -> bool:
    """Test extract_id_from_link when link has no href attribute"""
    print("Testing extract_id_from_link with no href attribute...")
    try:
        # Create HTML with link without href
        html_content = """
        <html>
        <body>
            <a>Link without href</a>
        </body>
        </html>
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        link_element = soup.find('a')
        
        # Test extracting ID from link without href
        result = extract_id_from_link(link_element)
        expected = None
        if result == expected:
            print(f"  ✓ Correctly returned None for link without href")
            return True
        else:
            print(f"  ✗ Expected '{expected}', got '{result}'")
            return False
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False

async def test_extract_id_from_link_no_match(session: aiohttp.ClientSession) -> bool:
    """Test extract_id_from_link when pattern doesn't match"""
    print("Testing extract_id_from_link when pattern doesn't match...")
    try:
        # Create HTML with href that doesn't match pattern
        html_content = """
        <html>
        <body>
            <a href="https://example.com/page">Link</a>
        </body>
        </html>
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        link_element = soup.find('a')
        
        # Test extracting ID when pattern doesn't match
        result = extract_id_from_link(link_element)
        expected = None
        if result == expected:
            print(f"  ✓ Correctly returned None when pattern doesn't match")
            return True
        else:
            print(f"  ✗ Expected '{expected}', got '{result}'")
            return False
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False

async def test_extract_ids_from_links_basic(session: aiohttp.ClientSession) -> bool:
    """Test basic functionality of extract_ids_from_links function"""
    print("Testing extract_ids_from_links basic functionality...")
    try:
        # Create HTML with multiple links
        html_content = """
        <html>
        <body>
            <a href="edit.asp?id=12345">Link 1</a>
            <a href="edit.asp?id=67890">Link 2</a>
            <a href="edit.asp?id=ABCDE">Link 3</a>
        </body>
        </html>
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Test extracting IDs from multiple links
        result = extract_ids_from_links(soup)
        expected = ["12345", "67890", "ABCDE"]
        if result == expected:
            print(f"  ✓ Extracted {result} correctly")
            return True
        else:
            print(f"  ✗ Expected {expected}, got {result}")
            return False
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False

async def test_extract_ids_from_links_with_custom_pattern(session: aiohttp.ClientSession) -> bool:
    """Test extract_ids_from_links with custom pattern"""
    print("Testing extract_ids_from_links with custom pattern...")
    try:
        # Create HTML with custom ID patterns
        html_content = """
        <html>
        <body>
            <a href="view.php?patient=ABC123&tab=details">Link 1</a>
            <a href="view.php?patient=DEF456&tab=details">Link 2</a>
        </body>
        </html>
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Test extracting IDs with custom pattern
        result = extract_ids_from_links(soup, r'patient=([^&"]+)')
        expected = ["ABC123", "DEF456"]
        if result == expected:
            print(f"  ✓ Extracted {result} correctly with custom pattern")
            return True
        else:
            print(f"  ✗ Expected {expected}, got {result}")
            return False
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False

async def test_extract_ids_from_links_no_matches(session: aiohttp.ClientSession) -> bool:
    """Test extract_ids_from_links when no links match pattern"""
    print("Testing extract_ids_from_links when no links match pattern...")
    try:
        # Create HTML with links that don't match pattern
        html_content = """
        <html>
        <body>
            <a href="https://example.com/page1">Link 1</a>
            <a href="https://example.com/page2">Link 2</a>
        </body>
        </html>
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Test extracting IDs when no links match
        result = extract_ids_from_links(soup)
        expected = []
        if result == expected:
            print(f"  ✓ Correctly returned empty list when no links match")
            return True
        else:
            print(f"  ✗ Expected {expected}, got {result}")
            return False
    except Exception as e:
        print(f"  ✗ Test failed with exception: {e}")
        return False
