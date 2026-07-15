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


ExtractedRecord = Union[ImagingRecord, InterventionRecord, ClinicalNoteRecord]

SCHEMAS: dict[str, type[BaseModel]] = {
    "imaging": ImagingRecord,
    "intervention": InterventionRecord,
    "clinical_note": ClinicalNoteRecord,
}


def model_extraction_schema(record_cls: type[BaseModel]) -> dict:
    """JSON schema sent to the model/grammar — excludes pipeline-only fields."""
    schema = record_cls.model_json_schema()
    for field in ("needs_review", "raw_source"):
        schema.get("properties", {}).pop(field, None)
    if "required" in schema:
        schema["required"] = [f for f in schema["required"] if f not in ("needs_review", "raw_source")]
    return schema
