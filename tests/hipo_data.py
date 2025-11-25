import unittest
from hipo import HipoData

class TestHipoData(unittest.TestCase):
    """Test cases for the HipoData class and its new methods."""
    
    def setUp(self):
        """Set up test data."""
        self.hipo_data = HipoData()
    
    def test_get_section_key_with_valid_format(self):
        """Test get_section_key with valid section,key format."""
        section, key = self.hipo_data.get_section_key("patient,name")
        self.assertEqual(section, "patient")
        self.assertEqual(key, "name")
    
    def test_get_section_key_with_no_comma(self):
        """Test get_section_key with no comma in string."""
        section, key = self.hipo_data.get_section_key("patient")
        self.assertEqual(section, "patient")
        self.assertIsNone(key)
    
    def test_get_section_key_with_extra_spaces(self):
        """Test get_section_key with extra spaces."""
        section, key = self.hipo_data.get_section_key(" patient , name ")
        self.assertEqual(section, "patient")
        self.assertEqual(key, "name")
    
    def test_get_method_with_existing_value(self):
        """Test get method with existing section and key."""
        # Set up test data
        self.hipo_data["patient"] = {"name": "John Doe"}
        
        # Test getting existing value
        result = self.hipo_data.get("patient,name")
        self.assertEqual(result, "John Doe")
    
    def test_get_method_with_non_existing_section(self):
        """Test get method with non-existing section."""
        result = self.hipo_data.get("patient,name")
        self.assertEqual(result, "")
    
    def test_get_method_with_non_existing_key(self):
        """Test get method with existing section but non-existing key."""
        # Set up test data
        self.hipo_data["patient"] = {}
        
        result = self.hipo_data.get("patient,name")
        self.assertEqual(result, "")
    
    def test_get_method_with_key_none(self):
        """Test get method when key is None (section only)."""
        # Set up test data
        self.hipo_data["patient"] = "John Doe"
        
        result = self.hipo_data.get("patient")
        self.assertEqual(result, "John Doe")
    
    def test_get_method_with_key_none_not_existing(self):
        """Test get method when key is None and section doesn't exist."""
        result = self.hipo_data.get("patient")
        self.assertEqual(result, "")
    
    def test_get_method_with_non_string_value(self):
        """Test get method with non-string value."""
        # Set up test data
        self.hipo_data["patient"] = {"age": 30}
        
        result = self.hipo_data.get("patient,age")
        self.assertEqual(result, "30")
    
    def test_set_method_with_valid_section_and_key(self):
        """Test set method with valid section and key."""
        self.hipo_data.set("patient,name", "John Doe")
        
        self.assertIn("patient", self.hipo_data)
        self.assertIsInstance(self.hipo_data["patient"], dict)
        self.assertIn("name", self.hipo_data["patient"])
        self.assertEqual(self.hipo_data["patient"]["name"], "John Doe")
    
    def test_set_method_with_key_none(self):
        """Test set method when key is None (section only)."""
        self.hipo_data.set("patient", "John Doe")
        
        self.assertIn("patient", self.hipo_data)
        self.assertEqual(self.hipo_data["patient"], "John Doe")
    
    def test_set_method_creates_section_automatically(self):
        """Test that set method creates section automatically."""
        self.hipo_data.set("patient,name", "John Doe")
        
        self.assertIn("patient", self.hipo_data)
        self.assertIsInstance(self.hipo_data["patient"], dict)
    
    def test_set_method_overwrites_existing_value(self):
        """Test that set method overwrites existing values."""
        # Set initial value
        self.hipo_data.set("patient,name", "John Doe")
        
        # Overwrite with new value
        self.hipo_data.set("patient,name", "Jane Smith")
        
        self.assertEqual(self.hipo_data["patient"]["name"], "Jane Smith")

if __name__ == '__main__':
    unittest.main()
