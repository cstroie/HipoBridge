#!/usr/bin/env python3
""" FHIR Data Types Implementation """

from typing import Any, Dict, List, Optional
from collections.abc import MutableMapping


class Resource(MutableMapping):
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
        """Convert to dict, recursively converting Resource objects to dicts"""
        result = {}
        for k, v in self.data.items():
            if v is not None:
                if isinstance(v, Resource):
                    result[k] = v.to_dict()
                elif isinstance(v, list):
                    result[k] = [item.to_dict() if isinstance(item, Resource) else item for item in v]
                else:
                    result[k] = v
        return result

class Coding(Resource):
    def __init__(self, system: Optional[str] = None, version: Optional[str] = None, code: Optional[str] = None, 
                 display: Optional[str] = None, userSelected: Optional[bool] = None):
        data = {
            "system": system,             # Identity of the terminology system
            "version": version,           # Version of the system - if relevant
            "code": code,                 # Symbol in syntax defined by the system
            "display": display,           # Representation defined by the system
            "userSelected": userSelected  # If this coding was chosen directly by the user
        }
        super().__init__(data)


class CodeableReference(Resource):
    def __init__(self, concept: Optional[Dict[str, Any]] = None, reference: Optional[Dict[str, Any]] = None):
        data = {
            "concept": concept,         # Reference to a concept (by class)
            "reference": reference      # Reference to a resource (by instance)
        }
        super().__init__(data)


class CodeableConcept(Resource):
    def __init__(self, coding: Optional[List[Dict[str, Any]]] = None, text: Optional[str] = None):
        data = {
            "coding": coding,           # Code defined by a terminology system
            "text": text                # Plain text representation of the concept
        }
        super().__init__(data)


class Identifier(Resource):
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


class HumanName(Resource):
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


class Reference(Resource):
    def __init__(self, reference: Optional[str] = None, type: Optional[str] = None,
                 identifier: Optional[Dict[str, Any]] = None, display: Optional[str] = None):
        data = {
            "reference": reference,     # Literal reference, Relative, internal or absolute URL
            "type": type,               # Type the reference refers to (e.g. "Patient") - must be a resource in resources
            "identifier": identifier,   # Logical reference, when literal reference is not known
            "display": display          # Text alternative for the resource
        }
        super().__init__(data)


class Period(Resource):
    def __init__(self, start: Optional[str] = None, end: Optional[str] = None):
        data = {
            "start": start,             # Starting time with inclusive boundary
            "end": end                  # End time with inclusive boundary, if not ongoing
        }
        super().__init__(data)


class Address(Resource):
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


class ContactPoint(Resource):
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


class Annotation(Resource):
    def __init__(self, authorReference: Optional[Dict[str, Any]] = None, authorString: Optional[str] = None,
                 time: Optional[str] = None, text: Optional[str] = None):
        data = {
            "authorReference": authorReference,  # Individual responsible for the annotation
            "authorString": authorString,        # Individual responsible for the annotation
            "time": time,                        # When the annotation was made
            "text": text                         # The annotation - text content (as markdown)
        }
        super().__init__(data)


class Patient(Resource):
    def __init__(self, 
                 id: Optional[str] = None,
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
            "resourceType": "Patient",                          # Resource type
            "id": id,                                           # Logical id of this artifact
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


class Practitioner(Resource):
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
                 photo: Optional[List[Dict[str, Any]]] = None,
                 qualification: Optional[List[Dict[str, Any]]] = None,
                 communication: Optional[List[Dict[str, Any]]] = None):
        data = {
            "identifier": identifier,                           # An identifier for the person as this agent
            "active": active,                                   # Whether this practitioner's record is in active use
            "name": name,                                       # The name(s) associated with the practitioner
            "telecom": telecom,                                 # A contact detail for the practitioner (that apply to all roles)
            "gender": gender,                                   # male | female | other | unknown
            "birthDate": birthDate,                             # The date  on which the practitioner was born
            "deceasedBoolean": deceasedBoolean,                 # Indicates if the practitioner is deceased or not
            "deceasedDateTime": deceasedDateTime,               # Indicates if the practitioner is deceased or not
            "address": address,                                 # Address(es) of the practitioner that are not role specific (typically home address)
            "photo": photo,                                     # Image of the person
            "qualification": qualification,                     # Qualifications, certifications, accreditations, licenses, training, etc.
            "communication": communication                      # A language which may be used to communicate with the practitioner
        }
        super().__init__(data)


class OrderDetail(Resource):
    def __init__(self,
                 parameterFocusCodeableConcept: Optional[Dict[str, Any]] = None,
                 parameterFocusReference: Optional[Dict[str, Any]] = None,
                 parameterFocusCanonical: Optional[str] = None,
                 parameter: Optional[List[Dict[str, Any]]] = None):
        data = {
            "parameterFocusCodeableConcept": parameterFocusCodeableConcept,  # The context of the order details by reference
            "parameterFocusReference": parameterFocusReference,              # The context of the order details by reference
            "parameterFocusCanonical": parameterFocusCanonical,              # The context of the order details by reference
            "parameter": parameter                                           # The parameter details for the service being requested
        }
        super().__init__(data)


class ServiceRequest(Resource):
    def __init__(self,
                 id: Optional[str] = None,
                 identifier: Optional[List[Dict[str, Any]]] = None,
                 basedOn: Optional[List[Dict[str, Any]]] = None,
                 replaces: Optional[List[Dict[str, Any]]] = None,
                 requisition: Optional[Dict[str, Any]] = None,
                 status: Optional[str] = None,
                 statusReason: Optional[List[Dict[str, Any]]] = None,
                 intent: Optional[str] = None,
                 category: Optional[List[Dict[str, Any]]] = None,
                 priority: Optional[str] = None,
                 doNotPerform: Optional[bool] = None,
                 code: Optional[Dict[str, Any]] = None,
                 orderDetail: Optional[List[Dict[str, Any]]] = None,
                 quantityQuantity: Optional[Dict[str, Any]] = None,
                 quantityRatio: Optional[Dict[str, Any]] = None,
                 quantityRange: Optional[Dict[str, Any]] = None,
                 subject: Optional[Dict[str, Any]] = None,
                 focus: Optional[List[Dict[str, Any]]] = None,
                 encounter: Optional[Dict[str, Any]] = None,
                 occurrenceDateTime: Optional[str] = None,
                 occurrencePeriod: Optional[Dict[str, Any]] = None,
                 occurrenceTiming: Optional[Dict[str, Any]] = None,
                 asNeeded: Optional[bool] = None,
                 asNeededFor: Optional[List[Dict[str, Any]]] = None,
                 authoredOn: Optional[str] = None,
                 requester: Optional[Dict[str, Any]] = None,
                 performerType: Optional[Dict[str, Any]] = None,
                 performer: Optional[List[Dict[str, Any]]] = None,
                 location: Optional[List[Dict[str, Any]]] = None,
                 reason: Optional[List[Dict[str, Any]]] = None,
                 insurance: Optional[List[Dict[str, Any]]] = None,
                 supportingInfo: Optional[List[Dict[str, Any]]] = None,
                 specimen: Optional[List[Dict[str, Any]]] = None,
                 bodyStructure: Optional[Dict[str, Any]] = None,
                 note: Optional[List[Dict[str, Any]]] = None,
                 patientInstruction: Optional[List[Dict[str, Any]]] = None,
                 relevantHistory: Optional[List[Dict[str, Any]]] = None):
        data = {
            "resourceType": "ServiceRequest",                   # Resource type
            "id": id,                                           # Logical id of this artifact
            "identifier": identifier,                           # Identifiers assigned to this order
            "basedOn": basedOn,                                 # What request fulfills
            "replaces": replaces,                               # What request replaces
            "requisition": requisition,                         # Composite Request ID
            "status": status,                                   # draft | active | on-hold | entered-in-error | ended | completed | revoked | unknown
            "statusReason": statusReason,                       # Reason for current status
            "intent": intent,                                   # proposal | solicit-offer | offer-response | plan | directive | order | original-order | reflex-order | filler-order | instance-order | option
            "category": category,                               # Classification of service
            "priority": priority,                               # routine | urgent | asap | stat
            "doNotPerform": doNotPerform,                       # True if service/procedure should not be performed
            "code": code,                                       # What is being requested/ordered
            "orderDetail": orderDetail,                         # Additional information about the request
            "quantityQuantity": quantityQuantity,               # Service amount
            "quantityRatio": quantityRatio,                     # Service amount
            "quantityRange": quantityRange,                     # Service amount
            "subject": subject,                                 # Individual or Entity the service is ordered for
            "focus": focus,                                     # What the service request is about, when it is not about the subject of record
            "encounter": encounter,                             # Encounter in which the request was created
            "occurrenceDateTime": occurrenceDateTime,           # When service should occur
            "occurrencePeriod": occurrencePeriod,               # When service should occur
            "occurrenceTiming": occurrenceTiming,               # When service should occur
            "asNeeded": asNeeded,                               # Perform the service "as needed"
            "asNeededFor": asNeededFor,                         # Specified criteria for the service
            "authoredOn": authoredOn,                           # Date request signed
            "requester": requester,                             # Who/what is requesting service
            "performerType": performerType,                     # Performer role
            "performer": performer,                             # Requested performer
            "location": location,                               # Requested location
            "reason": reason,                                   # Reason or indication for requesting the service
            "insurance": insurance,                             # Associated insurance coverage
            "supportingInfo": supportingInfo,                   # Additional clinical information
            "specimen": specimen,                               # Procedure Samples
            "bodyStructure": bodyStructure,                     # BodyStructure-based location on the body
            "note": note,                                       # Comments
            "patientInstruction": patientInstruction,           # Patient or consumer-oriented instructions
            "relevantHistory": relevantHistory                  # Request provenance
        }
        super().__init__(data)


class Condition(Resource):
    def __init__(self,
                 identifier: Optional[List[Dict[str, Any]]] = None,
                 clinicalStatus: Optional[Dict[str, Any]] = None,
                 verificationStatus: Optional[Dict[str, Any]] = None,
                 category: Optional[List[Dict[str, Any]]] = None,
                 severity: Optional[Dict[str, Any]] = None,
                 code: Optional[Dict[str, Any]] = None,
                 bodySite: Optional[List[Dict[str, Any]]] = None,
                 bodyStructure: Optional[Dict[str, Any]] = None,
                 subject: Optional[Dict[str, Any]] = None,
                 encounter: Optional[Dict[str, Any]] = None,
                 onsetDateTime: Optional[str] = None,
                 onsetAge: Optional[Dict[str, Any]] = None,
                 onsetPeriod: Optional[Dict[str, Any]] = None,
                 onsetRange: Optional[Dict[str, Any]] = None,
                 onsetString: Optional[str] = None,
                 abatementDateTime: Optional[str] = None,
                 abatementAge: Optional[Dict[str, Any]] = None,
                 abatementPeriod: Optional[Dict[str, Any]] = None,
                 abatementRange: Optional[Dict[str, Any]] = None,
                 abatementString: Optional[str] = None,
                 recordedDate: Optional[str] = None,
                 recorder: Optional[Dict[str, Any]] = None,
                 asserter: Optional[Dict[str, Any]] = None,
                 stage: Optional[List[Dict[str, Any]]] = None,
                 evidence: Optional[List[Dict[str, Any]]] = None,
                 note: Optional[List[Dict[str, Any]]] = None):
        data = {
            "resourceType": "Condition",                        # Resource type
            "identifier": identifier,                           # External Ids for this condition
            "clinicalStatus": clinicalStatus,                   # active | recurrence | relapse | inactive | remission | resolved | unknown
            "verificationStatus": verificationStatus,           # unconfirmed | provisional | differential | confirmed | refuted | entered-in-error
            "category": category,                               # problem-list-item | encounter-diagnosis
            "severity": severity,                               # Subjective severity of condition
            "code": code,                                       # Identification of the condition, problem or diagnosis
            "bodySite": bodySite,                               # Anatomical location, if relevant
            "bodyStructure": bodyStructure,                     # Anatomical body structure
            "subject": subject,                                 # Who has the condition?
            "encounter": encounter,                             # The Encounter during which this Condition was created
            "onsetDateTime": onsetDateTime,                     # Estimated or actual date, date-time, or age
            "onsetAge": onsetAge,                               # Estimated or actual date, date-time, or age
            "onsetPeriod": onsetPeriod,                         # Estimated or actual date, date-time, or age
            "onsetRange": onsetRange,                           # Estimated or actual date, date-time, or age
            "onsetString": onsetString,                         # Estimated or actual date, date-time, or age
            "abatementDateTime": abatementDateTime,             # When in resolution/remission
            "abatementAge": abatementAge,                       # When in resolution/remission
            "abatementPeriod": abatementPeriod,                 # When in resolution/remission
            "abatementRange": abatementRange,                   # When in resolution/remission
            "abatementString": abatementString,                 # When in resolution/remission
            "recordedDate": recordedDate,                       # Date condition was first recorded
            "recorder": recorder,                               # Who recorded the condition
            "asserter": asserter,                               # Person or device that asserts this condition
            "stage": stage,                                     # Stage/grade, usually assessed formally
            "evidence": evidence,                               # Supporting evidence for the condition
            "note": note                                        # Additional information about the Condition
        }
        super().__init__(data)


class Procedure(Resource):
    def __init__(self,
                 identifier: Optional[List[Dict[str, Any]]] = None,
                 basedOn: Optional[List[Dict[str, Any]]] = None,
                 partOf: Optional[List[Dict[str, Any]]] = None,
                 status: Optional[str] = None,
                 statusReason: Optional[Dict[str, Any]] = None,
                 category: Optional[List[Dict[str, Any]]] = None,
                 code: Optional[Dict[str, Any]] = None,
                 subject: Optional[Dict[str, Any]] = None,
                 focus: Optional[Dict[str, Any]] = None,
                 encounter: Optional[Dict[str, Any]] = None,
                 occurrenceDateTime: Optional[str] = None,
                 occurrencePeriod: Optional[Dict[str, Any]] = None,
                 occurrenceString: Optional[str] = None,
                 occurrenceAge: Optional[Dict[str, Any]] = None,
                 occurrenceRange: Optional[Dict[str, Any]] = None,
                 occurrenceTiming: Optional[Dict[str, Any]] = None,
                 recorded: Optional[str] = None,
                 recorder: Optional[Dict[str, Any]] = None,
                 reportedBoolean: Optional[bool] = None,
                 reportedReference: Optional[Dict[str, Any]] = None,
                 performer: Optional[List[Dict[str, Any]]] = None,
                 location: Optional[Dict[str, Any]] = None,
                 reason: Optional[List[Dict[str, Any]]] = None,
                 bodySite: Optional[List[Dict[str, Any]]] = None,
                 bodyStructure: Optional[Dict[str, Any]] = None,
                 outcome: Optional[List[Dict[str, Any]]] = None,
                 report: Optional[List[Dict[str, Any]]] = None,
                 complication: Optional[List[Dict[str, Any]]] = None,
                 followUp: Optional[List[Dict[str, Any]]] = None,
                 note: Optional[List[Dict[str, Any]]] = None,
                 focalDevice: Optional[List[Dict[str, Any]]] = None,
                 used: Optional[List[Dict[str, Any]]] = None,
                 supportingInfo: Optional[List[Dict[str, Any]]] = None):
        data = {
            "identifier": identifier,                           # External Identifiers for this procedure
            "basedOn": basedOn,                                 # A request for this procedure
            "partOf": partOf,                                   # Part of referenced event
            "status": status,                                   # preparation | in-progress | not-done | on-hold | stopped | completed | entered-in-error | unknown
            "statusReason": statusReason,                       # Reason for current status
            "category": category,                               # Classification of the procedure
            "code": code,                                       # Identification of the procedure
            "subject": subject,                                 # Individual or entity the procedure was performed on
            "focus": focus,                                     # Who is the target of the procedure when it is not the subject of record only
            "encounter": encounter,                             # The Encounter during which this Procedure was created
            "occurrenceDateTime": occurrenceDateTime,           # When the procedure occurred or is occurring
            "occurrencePeriod": occurrencePeriod,               # When the procedure occurred or is occurring
            "occurrenceString": occurrenceString,               # When the procedure occurred or is occurring
            "occurrenceAge": occurrenceAge,                     # When the procedure occurred or is occurring
            "occurrenceRange": occurrenceRange,                 # When the procedure occurred or is occurring
            "occurrenceTiming": occurrenceTiming,               # When the procedure occurred or is occurring
            "recorded": recorded,                               # When the procedure was first captured in the subject's record
            "recorder": recorder,                               # Who recorded the procedure
            "reportedBoolean": reportedBoolean,                 # Reported rather than primary record
            "reportedReference": reportedReference,             # Reported rather than primary record
            "performer": performer,                             # Who performed the procedure and what they did
            "location": location,                               # Where the procedure happened
            "reason": reason,                                   # The justification that the procedure was performed
            "bodySite": bodySite,                               # Target body sites
            "bodyStructure": bodyStructure,                     # Target body structure
            "outcome": outcome,                                 # The result of procedure
            "report": report,                                   # Any report resulting from the procedure
            "complication": complication,                       # Complication following the procedure
            "followUp": followUp,                               # Instructions for follow up
            "note": note,                                       # Additional information about the procedure
            "focalDevice": focalDevice,                         # Manipulated, implanted, or removed device
            "used": used,                                       # Items used during procedure
            "supportingInfo": supportingInfo                    # Extra information relevant to the procedure
        }
        super().__init__(data)


class Performer(Resource):
    def __init__(self,
                 function: Optional[Dict[str, Any]] = None,
                 actor: Optional[Dict[str, Any]] = None):
        data = {
            "function": function,     # Type of performance
            "actor": actor            # Who performed imaging study
        }
        super().__init__(data)


class SOPInstance(Resource):
    def __init__(self,
                 uid: Optional[str] = None,
                 sopClass: Optional[str] = None,
                 number: Optional[int] = None,
                 title: Optional[str] = None):
        data = {
            "uid": uid,               # DICOM SOP Instance UID
            "sopClass": sopClass,     # DICOM class type
            "number": number,         # The number of this instance in the series
            "title": title            # Name or title of the instance
        }
        super().__init__(data)


class Series(Resource):
    def __init__(self,
                 uid: Optional[str] = None,
                 number: Optional[int] = None,
                 modality: Optional[Dict[str, Any]] = None,
                 description: Optional[str] = None,
                 numberOfInstances: Optional[int] = None,
                 endpoint: Optional[List[Dict[str, Any]]] = None,
                 bodySite: Optional[Dict[str, Any]] = None,
                 specimen: Optional[List[Dict[str, Any]]] = None,
                 started: Optional[str] = None,
                 performer: Optional[List[Dict[str, Any]]] = None,
                 instance: Optional[List[Dict[str, Any]]] = None):
        data = {
            "uid": uid,                           # DICOM Series Instance UID
            "number": number,                     # Numeric identifier of this series
            "modality": modality,                 # The modality used for this series
            "description": description,           # Series Description or Classification
            "numberOfInstances": numberOfInstances,  # Number of Series Related Instances
            "endpoint": endpoint,                 # Series access endpoint
            "bodySite": bodySite,                 # Body part examined
            "specimen": specimen,                 # Specimen imaged
            "started": started,                   # When the series started
            "performer": performer,               # Who performed the series
            "instance": instance                  # A single SOP instance from the series
        }
        super().__init__(data)


class SupportingInfo(Resource):
    def __init__(self,
                 type: Optional[Dict[str, Any]] = None,
                 reference: Optional[Dict[str, Any]] = None):
        data = {
            "type": type,                         # Supporting information role code
            "reference": reference                # Supporting information reference
        }
        super().__init__(data)


class ImagingStudy(Resource):
    def __init__(self,
                 identifier: Optional[List[Dict[str, Any]]] = None,
                 status: Optional[str] = None,
                 modality: Optional[List[Dict[str, Any]]] = None,
                 subject: Optional[Dict[str, Any]] = None,
                 encounter: Optional[Dict[str, Any]] = None,
                 started: Optional[str] = None,
                 basedOn: Optional[List[Dict[str, Any]]] = None,
                 procedure: Optional[List[Dict[str, Any]]] = None,
                 referrer: Optional[Dict[str, Any]] = None,
                 endpoint: Optional[List[Dict[str, Any]]] = None,
                 location: Optional[Dict[str, Any]] = None,
                 reason: Optional[List[Dict[str, Any]]] = None,
                 note: Optional[List[Dict[str, Any]]] = None,
                 description: Optional[str] = None,
                 numberOfSeries: Optional[int] = None,
                 numberOfInstances: Optional[int] = None,
                 series: Optional[List[Dict[str, Any]]] = None):
        data = {
            "resourceType": "ImagingStudy",       # Resource type
            "identifier": identifier,             # Business identifier for imaging study
            "status": status,                     # registered | available | cancelled | entered-in-error | unknown | inactive
            "modality": modality,                 # The distinct values for series' modalities
            "subject": subject,                   # Who or what is the subject of the study
            "encounter": encounter,               # Encounter with which this imaging study is associated
            "started": started,                   # When the study was started
            "basedOn": basedOn,                   # Fulfills plan or order
            "procedure": procedure,               # Imaging performed procedure(s)
            "referrer": referrer,                 # Referring physician
            "endpoint": endpoint,                 # Study access endpoint
            "location": location,                 # Where imaging study occurred
            "reason": reason,                     # Why was imaging study performed?
            "note": note,                         # Comments made about the imaging study
            "description": description,           # Study Description or Classification
            "numberOfSeries": numberOfSeries,     # Number of Study Related Series
            "numberOfInstances": numberOfInstances,  # Number of Study Related Instances
            "series": series                      # The set of Series belonging to the study
        }
        super().__init__(data)


class DiagnosticReport(Resource):
    def __init__(self,
                 identifier: Optional[List[Dict[str, Any]]] = None,
                 basedOn: Optional[List[Dict[str, Any]]] = None,
                 status: Optional[str] = None,
                 category: Optional[List[Dict[str, Any]]] = None,
                 code: Optional[Dict[str, Any]] = None,
                 subject: Optional[Dict[str, Any]] = None,
                 relatesTo: Optional[List[Dict[str, Any]]] = None,
                 encounter: Optional[Dict[str, Any]] = None,
                 effectiveDateTime: Optional[str] = None,
                 effectivePeriod: Optional[Dict[str, Any]] = None,
                 issued: Optional[str] = None,
                 procedure: Optional[List[Dict[str, Any]]] = None,
                 performer: Optional[List[Dict[str, Any]]] = None,
                 resultsInterpreter: Optional[List[Dict[str, Any]]] = None,
                 specimen: Optional[List[Dict[str, Any]]] = None,
                 result: Optional[List[Dict[str, Any]]] = None,
                 note: Optional[List[Dict[str, Any]]] = None,
                 study: Optional[List[Dict[str, Any]]] = None,
                 supportingInfo: Optional[List[Dict[str, Any]]] = None,
                 composition: Optional[Dict[str, Any]] = None,
                 conclusion: Optional[str] = None,
                 conclusionCode: Optional[List[Dict[str, Any]]] = None,
                 recomendation: Optional[List[Dict[str, Any]]] = None,
                 presentedForm: Optional[List[Dict[str, Any]]] = None,
                 communication: Optional[List[Dict[str, Any]]] = None,
                 comparison: Optional[Dict[str, Any]] = None):
        data = {
            "resourceType": "DiagnosticReport",   # Resource type
            "identifier": identifier,             # Business identifier for report
            "basedOn": basedOn,                   # What was requested
            "status": status,                     # registered | partial | preliminary | modified | final | amended | corrected | appended | cancelled | entered-in-error | unknown
            "category": category,                 # Service category
            "code": code,                         # Name/Code for this diagnostic report
            "subject": subject,                   # The subject of the report - usually, but not always, the patient
            "relatesTo": relatesTo,               # Related DiagnosticReports
            "encounter": encounter,               # Encounter associated with the DiagnosticReport
            "effectiveDateTime": effectiveDateTime,  # Clinically relevant time/time-period for the results
            "effectivePeriod": effectivePeriod,   # Clinically relevant time/time-period for the results
            "issued": issued,                     # DateTime this version was made
            "procedure": procedure,               # The performed procedure(s) from which the report was produced
            "performer": performer,               # Responsible Diagnostic Service
            "resultsInterpreter": resultsInterpreter,  # Who analyzed and reported the conclusions and interpretations
            "specimen": specimen,                 # Specimens this report is based on
            "result": result,                     # Observations
            "note": note,                         # Comments about the diagnostic report
            "study": study,                       # Reference to full details of an analysis associated with the diagnostic report
            "supportingInfo": supportingInfo,     # Additional information supporting the diagnostic report
            "composition": composition,           # Reference to a Composition resource for the DiagnosticReport structure
            "conclusion": conclusion,             # Clinical conclusion (interpretation) of test results
            "conclusionCode": conclusionCode,     # Codes and/or references for the clinical conclusion of test results
            "recomendation": recomendation,       # Recommendations based on findings and interpretations
            "presentedForm": presentedForm,       # Entire report as issued
            "communication": communication,       # Communication initiated during the reporting process
            "comparison": comparison              # Prior data and findings for comparison
        }
        super().__init__(data)


class Issue(Resource):
    def __init__(self, 
                 severity: str,
                 code: str,
                 details: Optional[Dict[str, Any]] = None,
                 diagnostics: Optional[str] = None,
                 location: Optional[List[str]] = None,
                 expression: Optional[List[str]] = None):
        data = {
            "severity": severity,           # fatal | error | warning | information | success
            "code": code,                   # Error or warning code
            "details": details,             # Additional details about the error
            "diagnostics": diagnostics,     # Additional diagnostic information about the issue
            "location": location,           # Deprecated: Path of element(s) related to issue
            "expression": expression        # FHIRPath of element(s) related to issue
        }
        super().__init__(data)


class Bundle(Resource):
    def __init__(self,
                 id: Optional[str] = None,
                 identifier: Optional[Dict[str, Any]] = None,
                 type: Optional[str] = None,
                 timestamp: Optional[str] = None,
                 total: Optional[int] = None,
                 link: Optional[List[Dict[str, Any]]] = None,
                 entry: Optional[List[Dict[str, Any]]] = None,
                 signature: Optional[Dict[str, Any]] = None,
                 issues: Optional[Dict[str, Any]] = None):
        data = {
            "resourceType": "Bundle",           # Resource type
            "id": id,                           # Logical id of this artifact
            "identifier": identifier,           # Persistent identifier for the bundle
            "type": type,                       # document | message | transaction | transaction-response | batch | batch-response | history | searchset | collection | subscription-notification
            "timestamp": timestamp,             # When the bundle was assembled
            "total": total,                     # Total matches across all pages
            "link": link,                       # Links related to this Bundle
            "entry": entry,                     # Entry in the bundle - will have a resource or information
            "signature": signature,             # Digital Signature (deprecated: use Provenance Signatures)
            "issues": issues                    # OperationOutcome with issues about the Bundle
        }
        super().__init__(data)
    
    def append_entry(self, resource: Resource, fullUrl: Optional[str] = None, 
                     search: Optional[Dict[str, Any]] = None, request: Optional[Dict[str, Any]] = None,
                     response: Optional[Dict[str, Any]] = None, entry_link: Optional[List[Dict[str, Any]]] = None):
        """Append an entry to the bundle.
        
        Args:
            resource: The resource to add to the bundle
            fullUrl: URI for resource (e.g. the absolute URL server address, URI for UUID/OID, etc.)
            search: Search related information
            request: Additional execution information (transaction/batch/history)
            response: Results of execution (transaction/batch/history)
            entry_link: Links related to this entry
        """
        entry = {
            "resource": resource.to_dict() if hasattr(resource, 'to_dict') else resource
        }
        
        if fullUrl:
            entry["fullUrl"] = fullUrl
        if search:
            entry["search"] = search
        if request:
            entry["request"] = request
        if response:
            entry["response"] = response
        if entry_link:
            entry["link"] = entry_link
            
        if self.data.get("entry") is None:
            self.data["entry"] = []
        self.data["entry"].append(entry)
    
    def set_total(self, total: int):
        """Set the total number of matches across all pages."""
        self.data["total"] = total
    
    def get_entry_count(self) -> int:
        """Get the number of entries in the bundle."""
        return len(self.data.get("entry", []))


class OperationOutcome(Resource):
    def __init__(self,
                 id: Optional[str] = None,
                 issue: Optional[List[Dict[str, Any]]] = None):
        data = {
            "resourceType": "OperationOutcome",   # Resource type
            "id": id,                             # Logical id of this artifact
            "issue": issue                        # A single issue associated with the action
        }
        super().__init__(data)
    
    @classmethod
    def from_error(cls, message: str, code: str = "exception", severity: str = "error", 
                   diagnostics: Optional[str] = None, location: Optional[List[str]] = None,
                   expression: Optional[List[str]] = None):
        """Create an OperationOutcome from an error message."""
        issue = Issue(
            severity=severity,
            code=code,
            details={"text": message},
            diagnostics=diagnostics,
            location=location,
            expression=expression
        )
        return cls(issue=[issue.to_dict()])
    
    @classmethod
    def from_exception(cls, exception: Exception, code: str = "exception", 
                       diagnostics: Optional[str] = None):
        """Create an OperationOutcome from an exception."""
        return cls.from_error(
            message=str(exception),
            code=code,
            severity="error",
            diagnostics=diagnostics or f"Exception type: {type(exception).__name__}"
        )
    
    def add_issue(self, severity: str, code: str, message: str,
                  diagnostics: Optional[str] = None, location: Optional[List[str]] = None,
                  expression: Optional[List[str]] = None):
        """Add an issue to the OperationOutcome."""
        issue = Issue(
            severity=severity,
            code=code,
            details={"text": message},
            diagnostics=diagnostics,
            location=location,
            expression=expression
        )
        
        if self.data.get("issue") is None:
            self.data["issue"] = []
        self.data["issue"].append(issue.to_dict())
    
    def has_errors(self) -> bool:
        """Check if the OperationOutcome has any error or fatal issues."""
        issues = self.data.get("issue", [])
        for issue in issues:
            if issue.get("severity") in ["error", "fatal"]:
                return True
        return False
    
    def has_warnings(self) -> bool:
        """Check if the OperationOutcome has any warning issues."""
        issues = self.data.get("issue", [])
        for issue in issues:
            if issue.get("severity") == "warning":
                return True
        return False

