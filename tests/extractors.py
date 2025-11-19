#!/usr/bin/env python3
"""
Extractor tests for the Hipocrate API
"""
import asyncio
import aiohttp
import os
from bs4 import BeautifulSoup
from hipp import extract_text_after_label

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
