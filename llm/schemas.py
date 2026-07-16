"""Pydantic schemas for LLM-extracted structured records.

Fields the model targets are kept minimal and null-friendly — small
models should never be pushed to invent a value. `needs_review` and
`raw_source` are added by the pipeline after generation, not sent to
the model as part of the JSON schema/grammar.
"""
import datetime
from typing import Literal, Union

from pydantic import BaseModel


class ImagingRecord(BaseModel):
    type: Literal["imaging"] = "imaging"
    date: datetime.date | None = None
    modality: str | None = None
    body_region: str | None = None
    findings: list[str] = []
    impression: str | None = None
    needs_review: bool = False
    raw_source: str = ""


class InterventionRecord(BaseModel):
    type: Literal["intervention"] = "intervention"
    date: datetime.date | None = None
    procedure: str | None = None
    outcome: str | None = None
    needs_review: bool = False
    raw_source: str = ""


class ClinicalNoteRecord(BaseModel):
    type: Literal["clinical_note"] = "clinical_note"
    date: datetime.date | None = None
    summary: str | None = None
    needs_review: bool = False
    raw_source: str = ""


class RadiologyImpressionRecord(BaseModel):
    type: Literal["radiology_impression"] = "radiology_impression"
    date: datetime.date | None = None
    modality: str | None = None
    body_region: str | None = None
    impression: str | None = None
    significant_findings: bool | None = None
    needs_review: bool = False
    raw_source: str = ""


class HomeMedication(BaseModel):
    drug_name: str | None = None
    dosage: str | None = None
    frequency: str | None = None


class DischargeRecord(BaseModel):
    type: Literal["discharge"] = "discharge"
    date: datetime.date | None = None
    executive_summary: str | None = None
    discharge_diagnoses: list[str] = []
    home_medications: list[HomeMedication] = []
    follow_up_instructions: str | None = None
    needs_review: bool = False
    raw_source: str = ""


class AbnormalLabValue(BaseModel):
    test_name: str | None = None
    value: str | None = None
    status: Literal["HIGH", "LOW", "CRITICAL"] | None = None


class LabPanelRecord(BaseModel):
    type: Literal["lab_panel"] = "lab_panel"
    date: datetime.date | None = None
    overall_summary: str | None = None
    abnormal_findings: list[AbnormalLabValue] = []
    needs_review: bool = False
    raw_source: str = ""


ExtractedRecord = Union[
    ImagingRecord, InterventionRecord, ClinicalNoteRecord,
    RadiologyImpressionRecord, DischargeRecord, LabPanelRecord,
]

SCHEMAS: dict[str, type[BaseModel]] = {
    "imaging": ImagingRecord,
    "intervention": InterventionRecord,
    "clinical_note": ClinicalNoteRecord,
    "radiology_impression": RadiologyImpressionRecord,
    "discharge": DischargeRecord,
    "lab_panel": LabPanelRecord,
}


def model_extraction_schema(record_cls: type[BaseModel]) -> dict:
    """JSON schema sent to the model/grammar — excludes pipeline-only fields."""
    schema = record_cls.model_json_schema()
    for field in ("needs_review", "raw_source"):
        schema.get("properties", {}).pop(field, None)
    if "required" in schema:
        schema["required"] = [f for f in schema["required"] if f not in ("needs_review", "raw_source")]
    return schema
