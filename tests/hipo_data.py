#!/usr/bin/env python3
"""Tests for the HipoData class."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from hipo import HipoData


class TestHipoData(unittest.TestCase):
    """Test cases for the HipoData class."""

    def setUp(self):
        """Set up test fixtures."""
        self.data = HipoData()

    def test_init_empty(self):
        """Test that HipoData initializes as an empty dictionary."""
        self.assertIsInstance(self.data, dict)
        self.assertEqual(len(self.data), 0)

    def test_store_in_root(self):
        """Test storing data directly in root."""
        self.data.store("name", "John Doe")
        self.assertEqual(self.data["name"], "John Doe")
        self.assertEqual(len(self.data), 1)

    def test_store_in_root_direct(self):
        """Test storing data directly in root."""
        self.data.store("diagnosis", "Healthy")
        self.assertEqual(self.data["diagnosis"], "Healthy")
        self.assertEqual(len(self.data), 1)

    def test_store_in_section(self):
        """Test storing data in a named section."""
        self.data.store("patient.id", "12345")
        self.assertIn("patient", self.data)
        self.assertIsInstance(self.data["patient"], dict)
        self.assertEqual(self.data["patient"]["id"], "12345")

    def test_store_multiple_values_in_same_section(self):
        """Test storing multiple values in the same section."""
        self.data.store("patient.id", "12345")
        self.data.store("patient.name", "John Doe")
        self.assertIn("patient", self.data)
        self.assertEqual(self.data["patient"]["id"], "12345")
        self.assertEqual(self.data["patient"]["name"], "John Doe")

    def test_store_creates_section_automatically(self):
        """Test that sections are created automatically when first referenced."""
        self.data.store("patient.id", "12345")
        self.assertIn("patient", self.data)
        self.assertIsInstance(self.data["patient"], dict)

    def test_store_unwraps_single_element_list(self):
        """Test that single element lists are automatically unwrapped."""
        self.data.store("patient.id", ["12345"])
        self.assertEqual(self.data["patient"]["id"], "12345")
        self.assertNotIsInstance(self.data["patient"]["id"], list)

    def test_store_does_not_unwrap_multi_element_list(self):
        """Test that multi-element lists are not unwrapped."""
        multi_element_list = ["12345", "67890"]
        self.data.store_list("patient.ids", multi_element_list)
        self.assertEqual(self.data["patient"]["ids"], multi_element_list)

    def test_store_strips_string_values(self):
        """Test that string values are automatically stripped."""
        self.data.store("patient.name", "  John Doe  ")
        self.assertEqual(self.data["patient"]["name"], "John Doe")

    def test_store_handles_empty_values(self):
        """Test handling of empty values."""
        self.data.store("patient.name", "")
        self.assertEqual(self.data["patient"]["name"], "")

    def test_store_handles_none_values(self):
        """Test handling of None values."""
        self.data.store("patient.name", None)
        self.assertIsNone(self.data["patient"]["name"])

    def test_store_with_none_value(self):
        """Test behavior when value is None."""
        self.data.store("test", None)
        self.assertIsNone(self.data["test"])

    def test_store_overwrites_existing_values(self):
        """Test that storing with the same key overwrites existing values."""
        self.data.store("patient.name", "John Doe")
        self.data.store("patient.name", "Jane Smith")
        self.assertEqual(self.data["patient"]["name"], "Jane Smith")

    def test_complex_storage_scenario(self):
        """Test a complex scenario with multiple sections and data types."""
        # Store in root
        self.data.store("report_id", "R001")
        
        # Store in patient section
        self.data.store("patient.id", ["P001"])
        self.data.store("patient.name", "  John Doe  ")
        
        # Store in diagnosis section
        self.data.store("diagnosis", "Healthy")
        
        # Store multiple values in test section
        self.data.store("test.glucose", "90 mg/dL")
        self.data.store("test.cholesterol", "180 mg/dL")
        
        # Store list data
        self.data.store_list("test.results", ["result1", "result2"])
        
        # Verify structure
        self.assertEqual(self.data["report_id"], "R001")
        self.assertEqual(self.data["patient"]["id"], "P001")
        self.assertEqual(self.data["patient"]["name"], "John Doe")
        self.assertEqual(self.data["diagnosis"], "Healthy")
        self.assertEqual(self.data["test"]["glucose"], "90 mg/dL")
        self.assertEqual(self.data["test"]["cholesterol"], "180 mg/dL")
        self.assertEqual(self.data["test"]["results"], ["result1", "result2"])

    def test_get_section_key_with_valid_format(self):
        """Test get_section_key with valid section.key format."""
        section, key = self.data.get_section_key("patient.name")
        self.assertEqual(section, "patient")
        self.assertEqual(key, "name")
    
    def test_get_section_key_with_no_dot(self):
        """Test get_section_key with no dot in string."""
        section, key = self.data.get_section_key("patient")
        self.assertEqual(section, "patient")
        self.assertIsNone(key)
    
    def test_get_section_key_with_extra_spaces(self):
        """Test get_section_key with extra spaces."""
        section, key = self.data.get_section_key(" patient.name ")
        self.assertEqual(section, "patient")
        self.assertEqual(key, "name")
    
    def test_get_method_with_existing_value(self):
        """Test get method with existing section and key."""
        # Set up test data using store method
        self.data.store("patient.name", "John Doe")
        
        # Test getting existing value
        result = self.data.get("patient.name")
        self.assertEqual(result, "John Doe")
    
    def test_get_method_with_non_existing_section(self):
        """Test get method with non-existing section."""
        result = self.data.get("patient.name")
        self.assertEqual(result, "")
    
    def test_get_method_with_non_existing_key(self):
        """Test get method with existing section but non-existing key."""
        # Set up test data
        self.data.store("patient", {})
        
        result = self.data.get("patient.name")
        self.assertEqual(result, "")
    
    def test_get_method_with_key_none(self):
        """Test get method when key is None (section only)."""
        # Set up test data
        self.data.store("patient", "John Doe")
        
        result = self.data.get("patient")
        self.assertEqual(result, "John Doe")
    
    def test_get_method_with_key_none_not_existing(self):
        """Test get method when key is None and section doesn't exist."""
        result = self.data.get("patient")
        self.assertEqual(result, "")
    
    def test_get_method_with_default_value(self):
        """Test get method with custom default value."""
        result = self.data.get("patient.name", "Unknown")
        self.assertEqual(result, "Unknown")
    
    def test_get_method_with_default_value_existing_key(self):
        """Test get method with custom default value for existing key."""
        # Set up test data
        self.data.store("patient.name", "John Doe")
        
        result = self.data.get("patient.name", "Unknown")
        self.assertEqual(result, "John Doe")
    
    def test_get_method_with_non_string_value(self):
        """Test get method with non-string value."""
        # Set up test data
        self.data.store("patient.age", 30)
        
        result = self.data.get("patient.age")
        self.assertEqual(result, "30")
    
    def test_set_method_with_valid_section_and_key(self):
        """Test set method with valid section and key."""
        self.data.set("patient.name", "John Doe")
        
        self.assertIn("patient", self.data)
        self.assertIsInstance(self.data["patient"], dict)
        self.assertIn("name", self.data["patient"])
        self.assertEqual(self.data["patient"]["name"], "John Doe")
    
    def test_set_method_with_key_none(self):
        """Test set method when key is None (section only)."""
        self.data.set("patient", "John Doe")
        
        self.assertIn("patient", self.data)
        self.assertEqual(self.data["patient"], "John Doe")
    
    def test_set_method_creates_section_automatically(self):
        """Test that set method creates section automatically."""
        self.data.set("patient.name", "John Doe")
        
        self.assertIn("patient", self.data)
        self.assertIsInstance(self.data["patient"], dict)
    
    def test_set_method_overwrites_existing_value(self):
        """Test that set method overwrites existing values."""
        # Set initial value
        self.data.set("patient.name", "John Doe")
        
        # Overwrite with new value
        self.data.set("patient.name", "Jane Smith")
        
        self.assertEqual(self.data["patient"]["name"], "Jane Smith")

if __name__ == '__main__':
    unittest.main()
