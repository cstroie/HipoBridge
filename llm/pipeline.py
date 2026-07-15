"""Orchestrates segment -> extract -> assemble -> narrate.

Sorting, timeline assembly, and numeric comparison are pure Python — the
model's job stays narrow: structured extraction from one block at a time.
"""
import asyncio
import logging
import re
import time
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from llm import audit
from llm.prompts import extract_clinical_note, extract_imaging, extract_intervention
from llm.prompts.compare_qualitative import build as build_compare_prompt
from llm.schemas import ClinicalNoteRecord, ImagingRecord, SCHEMAS, model_extraction_schema
from llm.segment import Block, segment

logger = logging.getLogger(__name__)

PROMPTS = {
    "imaging": extract_imaging,
    "intervention": extract_intervention,
    "clinical_note": extract_clinical_note,
    # unstructured/unrecognized blocks get a generic clinical-note pass
    "unknown": extract_clinical_note,
}

_EXTRACTION_TIER = "instruct"
_MM_RE = re.compile(r'(\d+(?:\.\d+)?)\s*mm')


@dataclass
class TimelineEntry:
    date: object
    record: BaseModel
    ordered: bool = True
    delta_note: str | None = None


@dataclass
class ExtractionResult:
    records: list[BaseModel]
    timeline: list[TimelineEntry] = field(default_factory=list)


async def extract_block(block: Block, router, max_tokens: int = 300) -> BaseModel:
    hint = block.hint_type if block.hint_type in PROMPTS else "unknown"
    prompt_module = PROMPTS[hint]
    schema_cls = SCHEMAS["clinical_note" if hint == "unknown" else hint]
    json_schema = model_extraction_schema(schema_cls)

    started = time.monotonic()
    backend_name = router.backend_name(_EXTRACTION_TIER)

    # Backend/transport failures (server down, malformed grammar, bad
    # response shape) must flag needs_review the same as a validation
    # failure — never let one block's transport error propagate and take
    # down extraction for the whole document (medical data: never silently
    # drop, but also never let one failure nuke everything else).
    try:
        raw = await router.chat(
            _EXTRACTION_TIER,
            prompt_module.build(block.text),
            json_schema=json_schema,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        logger.warning(f"backend call failed for block, flagging needs_review: {exc}")
        audit.log_extraction(block.text, _EXTRACTION_TIER, backend_name, "needs_review",
                              (time.monotonic() - started) * 1000)
        return schema_cls.model_construct(needs_review=True, raw_source=block.text)

    try:
        record = schema_cls.model_validate_json(raw)
        audit.log_extraction(block.text, _EXTRACTION_TIER, backend_name, "ok",
                              (time.monotonic() - started) * 1000)
        return record
    except ValidationError:
        try:
            raw_retry = await router.chat(
                _EXTRACTION_TIER,
                prompt_module.build(block.text, corrective=True),
                json_schema=json_schema,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            logger.warning(f"backend call failed on retry, flagging needs_review: {exc}")
            audit.log_extraction(block.text, _EXTRACTION_TIER, backend_name, "needs_review",
                                  (time.monotonic() - started) * 1000)
            return schema_cls.model_construct(needs_review=True, raw_source=block.text)
        try:
            record = schema_cls.model_validate_json(raw_retry)
            audit.log_extraction(block.text, _EXTRACTION_TIER, backend_name, "retried",
                                  (time.monotonic() - started) * 1000)
            return record
        except ValidationError:
            audit.log_extraction(block.text, _EXTRACTION_TIER, backend_name, "needs_review",
                                  (time.monotonic() - started) * 1000)
            return schema_cls.model_construct(needs_review=True, raw_source=block.text)


def _mm_value(record: BaseModel) -> float | None:
    if not isinstance(record, ImagingRecord):
        return None
    haystack = " ".join(f for f in (record.findings or []) if f) + " " + (record.impression or "")
    match = _MM_RE.search(haystack)
    return float(match.group(1)) if match else None


def assemble_timeline(records: list[BaseModel]) -> list[TimelineEntry]:
    dated = [r for r in records if getattr(r, "date", None) is not None]
    undated = [r for r in records if getattr(r, "date", None) is None]
    dated.sort(key=lambda r: r.date)

    entries = [TimelineEntry(date=r.date, record=r, ordered=True) for r in dated]
    entries += [TimelineEntry(date=None, record=r, ordered=False) for r in undated]

    prev_mm = None
    for entry in entries:
        if not entry.ordered:
            continue
        mm = _mm_value(entry.record)
        if mm is not None and prev_mm is not None:
            delta = mm - prev_mm
            if delta > 0:
                entry.delta_note = f"+{delta:.1f}mm vs prior"
            elif delta < 0:
                entry.delta_note = f"{delta:.1f}mm vs prior"
            else:
                entry.delta_note = "unchanged vs prior"
        if mm is not None:
            prev_mm = mm

    return entries


async def compare_qualitative(earlier: BaseModel, later: BaseModel, router,
                               comparison_tier: str = "thinking") -> str:
    """Fallback for qualitative imaging comparisons a numeric diff can't
    decide — feeds structured records only, never raw text; capped output."""
    messages = build_compare_prompt(earlier.model_dump(), later.model_dump())
    result = await router.chat(comparison_tier, messages, max_tokens=8, temperature=0.0)
    return result.strip().lower()


async def extract_document(document: str, router) -> ExtractionResult:
    blocks = segment(document)
    records = list(await asyncio.gather(*(extract_block(b, router) for b in blocks)))
    timeline = assemble_timeline(records)
    return ExtractionResult(records=records, timeline=timeline)


async def narrate_brief(records: list[BaseModel], router, max_sentences: int = 5,
                         narration_tier: str = "instruct") -> str:
    """The one free-composition step — feeds ALREADY-EXTRACTED structured
    records, never raw source text, and bounds output length."""
    summary_input = [r.model_dump() for r in records if not getattr(r, "needs_review", False)]
    messages = [
        {"role": "system", "content": (
            f"Write a clinical brief in at most {max_sentences} sentences, based only on "
            "the structured records provided. Do not invent findings not present in the data.")},
        {"role": "user", "content": str(summary_input)},
    ]
    return await router.chat(narration_tier, messages, max_tokens=max_sentences * 40, temperature=0.2)
