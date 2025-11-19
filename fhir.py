
#!/usr/bin/env python3
""" FHIR Data Types Implementation """

from typing import Any, Dict, List, Optional
from collections.abc import MutableMapping


class FHIRObject(MutableMapping):
    def __init__(self, data):
        # Filter out None values
        self.data = {k: v for k, v in data.items() if v is not None}
    
    def __getitem__(self, key):
        return self.data[key]
    
    def __setitem__(self, key, value):
        self.data[key] = value
    
    def __delitem__(self, key):
        del self.data[key]
    
    def __iter__(self):
        # Filter out None values when iterating
        return (k for k in self.data if self.data[k] is not None)
    
    def __len__(self):
        return sum(1 for k in self.data if self.data[k] is not None)
    
    def to_dict(self):
        """Convert to dict, excluding None values"""
        return {k: v for k, v in self.data.items() if v is not None}

class CodeableReference(FHIRObject):
    def __init__(self, reference: Optional[str] = None, type: Optional[str] = None, identifier: Optional[Dict[str, Any]] = None, display: Optional[str] = None):
        data = {
            "reference": reference,     # Literal reference, Relative, internal or absolute URL
            "type": type,               # Type the reference refers to (e.g. "Patient") - must be a resource in resources
            "identifier": identifier,   # Logical reference, when literal reference is not known
            "display": display          # Text alternative for the resource
        }
        super().__init__(data)


class Coding(FHIRObject):
    def __init__(self, system: Optional[str] = None, version: Optional[str] = None, code: Optional[str] = None, 
                 display: Optional[str] = None, userSelected: Optional[bool] = None):
        data = {
            "system": system,           # Identity of the terminology system
            "version": version,         # Version of the system - if relevant
            "code": code,               # Symbol in syntax defined by the system
            "display": display,         # Representation defined by the system
            "userSelected": userSelected  # If this coding was chosen directly by the user
        }
        super().__init__(data)


class CodeableConcept(FHIRObject):
    def __init__(self, coding: Optional[List[Dict[str, Any]]] = None, text: Optional[str] = None):
        data = {
            "coding": coding,           # Code defined by a terminology system
            "text": text               # Plain text representation of the concept
        }
        super().__init__(data)


class Identifier(FHIRObject):
    def __init__(self, use: Optional[str] = None, type: Optional[Dict[str, Any]] = None, 
                 system: Optional[str] = None, value: Optional[str] = None,
                 period: Optional[Dict[str, Any]] = None, assigner: Optional[Dict[str, Any]] = None):
        data = {
            "use": use,                 # usual | official | temp | secondary | old (If known)
            "type": type,               # Description of identifier
            "system": system,           # The namespace for the identifier value
            "value": value,             # The value that is unique
            "period": period,           # Time period when id is/was valid for use
            "assigner": assigner        # Organization that issued id (may be just text)
        }
        super().__init__(data)


class HumanName(FHIRObject):
    def __init__(self, use: Optional[str] = None, text: Optional[str] = None, 
                 family: Optional[str] = None, given: Optional[List[str]] = None,
                 prefix: Optional[List[str]] = None, suffix: Optional[List[str]] = None,
                 period: Optional[Dict[str, Any]] = None):
        data = {
            "use": use,                 # usual | official | temp | nickname | anonymous | old | maiden
            "text": text,               # Text representation of the full name
            "family": family,           # Family name (often called 'Surname')
            "given": given,             # Given names (not always 'first'). Includes middle names
            "prefix": prefix,           # Parts that come before the name
            "suffix": suffix,           # Parts that come after the name
            "period": period            # Time period when name was/is in use
        }
        super().__init__(data)


class Reference(FHIRObject):
    def __init__(self, reference: Optional[str] = None, type: Optional[str] = None,
                 identifier: Optional[Dict[str, Any]] = None, display: Optional[str] = None):
        data = {
            "reference": reference,     # Literal reference, Relative, internal or absolute URL
            "type": type,               # Type the reference refers to (e.g. "Patient") - must be a resource in resources
            "identifier": identifier,   # Logical reference, when literal reference is not known
            "display": display          # Text alternative for the resource
        }
        super().__init__(data)


class Period(FHIRObject):
    def __init__(self, start: Optional[str] = None, end: Optional[str] = None):
        data = {
            "start": start,             # Starting time with inclusive boundary
            "end": end                  # End time with inclusive boundary, if not ongoing
        }
        super().__init__(data)


class Address(FHIRObject):
    def __init__(self, use: Optional[str] = None, type: Optional[str] = None,
                 text: Optional[str] = None, line: Optional[List[str]] = None,
                 city: Optional[str] = None, district: Optional[str] = None,
                 state: Optional[str] = None, postalCode: Optional[str] = None,
                 country: Optional[str] = None, period: Optional[Dict[str, Any]] = None):
        data = {
            "use": use,                 # home | work | temp | old | billing - purpose of this address
            "type": type,               # postal | physical | both
            "text": text,               # Text representation of the address
            "line": line,               # Street name, number, direction & P.O. Box etc.
            "city": city,               # Name of city, town etc.
            "district": district,       # District name (aka county)
            "state": state,             # Sub-unit of country (abbreviations ok)
            "postalCode": postalCode,   # Postal code for area
            "country": country,         # Country (e.g. may be ISO 3166 2 or 3 letter code)
            "period": period            # Time period when address was/is in use
        }
        super().__init__(data)


class ContactPoint(FHIRObject):
    def __init__(self, system: Optional[str] = None, value: Optional[str] = None,
                 use: Optional[str] = None, rank: Optional[int] = None,
                 period: Optional[Dict[str, Any]] = None):
        data = {
            "system": system,           # phone | fax | email | pager | url | sms | other
            "value": value,             # The actual contact point details
            "use": use,                 # home | work | temp | old | mobile - purpose of this contact point
            "rank": rank,               # Specify preferred order of use (1 = highest)
            "period": period            # Time period when the contact point was/is in use
        }
        super().__init__(data)


class Annotation(FHIRObject):
    def __init__(self, authorReference: Optional[Dict[str, Any]] = None, authorString: Optional[str] = None,
                 time: Optional[str] = None, text: Optional[str] = None):
        data = {
            "authorReference": authorReference,  # Individual responsible for the annotation
            "authorString": authorString,        # Individual responsible for the annotation
            "time": time,                        # When the annotation was made
            "text": text                         # The annotation - text content (as markdown)
        }
        super().__init__(data)


class Patient(FHIRObject):
    def __init__(self, 
                 identifier: Optional[List[Dict[str, Any]]] = None,
                 active: Optional[bool] = None,
                 name: Optional[List[Dict[str, Any]]] = None,
                 telecom: Optional[List[Dict[str, Any]]] = None,
                 gender: Optional[str] = None,
                 birthDate: Optional[str] = None,
                 deceasedBoolean: Optional[bool] = None,
                 deceasedDateTime: Optional[str] = None,
                 address: Optional[List[Dict[str, Any]]] = None,
                 maritalStatus: Optional[Dict[str, Any]] = None,
                 multipleBirthBoolean: Optional[bool] = None,
                 multipleBirthInteger: Optional[int] = None,
                 photo: Optional[List[Dict[str, Any]]] = None,
                 contact: Optional[List[Dict[str, Any]]] = None,
                 communication: Optional[List[Dict[str, Any]]] = None,
                 generalPractitioner: Optional[List[Dict[str, Any]]] = None,
                 managingOrganization: Optional[Dict[str, Any]] = None,
                 link: Optional[List[Dict[str, Any]]] = None):
        data = {
            "identifier": identifier,                           # An identifier for this patient
            "active": active,                                   # Whether this patient's record is in active use
            "name": name,                                       # A name associated with the patient
            "telecom": telecom,                                 # A contact detail for the individual
            "gender": gender,                                   # male | female | other | unknown
            "birthDate": birthDate,                             # The date of birth for the individual
            "deceasedBoolean": deceasedBoolean,                 # Indicates if the individual is deceased
            "deceasedDateTime": deceasedDateTime,               # Indicates when the individual died
            "address": address,                                 # An address for the individual
            "maritalStatus": maritalStatus,                     # Marital (civil) status of a patient
            "multipleBirthBoolean": multipleBirthBoolean,       # Whether patient is part of a multiple birth
            "multipleBirthInteger": multipleBirthInteger,       # Whether patient is part of a multiple birth
            "photo": photo,                                     # Image of the patient
            "contact": contact,                                 # A contact party for the patient
            "communication": communication,                     # A language which may be used to communicate with the patient
            "generalPractitioner": generalPractitioner,         # Patient's nominated primary care provider
            "managingOrganization": managingOrganization,       # Organization that is the custodian of the patient record
            "link": link                                        # Link to another patient resource
        }
        super().__init__(data)

