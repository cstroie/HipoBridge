Here is all of the Modality Worklist (MWL) DICOM tag data organized into a single, comprehensive table for easy reference:

| DICOM Module | Data Field Name | DICOM Tag (Group, Element) | Description / Console Mapping |
|---|---|---|---|
| Patient Identification | Patient's Name | (0010,0010) | Patient Name |
| Patient Identification | Patient ID | (0010,0020) | Patient ID / MRN |
| Patient Demographics | Patient's Birth Date | (0010,0030) | Date of Birth |
| Patient Demographics | Patient's Sex | (0010,0040) | Patient Gender |
| Patient Demographics | Patient's Weight | (0010,1030) | Patient Weight |
| Patient Demographics | Medical Alerts | (0010,2000) | Medical warning flags |
| Patient Demographics | Patient Comments | (0010,4000) | Patient notes / Additional Info candidate |
| Imaging Service Request | Accession Number | (0008,0050) | Accession # (Order tracking ID) |
| Imaging Service Request | Referring Physician's Name | (0008,0090) | Referring Doctor |
| Imaging Service Request | Requesting Physician | (0032,1032) | Ordering Doctor / Additional Info candidate |
| Requested Procedure | Study Instance UID | (0020,000D) | Unique study identifier (Links exam to PACS) |
| Requested Procedure | Requested Procedure Description | (0032,1060) | Overall exam description |
| Requested Procedure | Requested Procedure ID | (0040,1001) | Specific procedure identifier |
| Scheduled Procedure Step | Scheduled Procedure Step Sequence | (0040,0100) | Main container sequence for scheduling info |
| Scheduled Procedure Step | Scheduled Station AE Title | (0040,0001) | Destination Modality AE Title |
| Scheduled Procedure Step | Scheduled Procedure Step Start Date | (0040,0002) | Appointment Date |
| Scheduled Procedure Step | Scheduled Procedure Step Start Time | (0040,0003) | Appointment Time |
| Scheduled Procedure Step | Modality | (0008,0060) | Must return "US" for Ultrasound |
| Scheduled Procedure Step | Scheduled Procedure Step Description | (0040,0007) | Specific step description / Additional Info target |
| Scheduled Procedure Step | Scheduled Procedure Step ID | (0040,0009) | Step tracking ID |

