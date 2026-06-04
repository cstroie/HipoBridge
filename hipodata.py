#!/usr/bin/env python3
"""HipoData class for storing structured medical data with section support.

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
"""

from datetime import datetime
from typing import Any
import logging

logger = logging.getLogger('HipoData')

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
        # Auto-unwrap single element lists
        if isinstance(value, list):
            if len(value) > 0 :
                value = value[0]
            else:
                value = None
        # Convert date_time to iso format
        if isinstance(value, datetime):
            value = value.isoformat()
        # Auto-strip string values
        if isinstance(value, str):
            value = value.strip()
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
            # Do not store None
            if value is not None:
                data[sub_key] = value
        else:
            # Store directly in root
            # Do not store None
            if value is not None:
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
            
            if not isinstance(value, list):
                value = [value]
                
            data[sub_key] = value
        else:
            # Store directly in root
            if not isinstance(value, list):
                value = [value]
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
