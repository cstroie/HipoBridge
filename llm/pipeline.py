"""Orchestrates segment -> extract -> assemble -> narrate.

Sorting, timeline assembly, and numeric comparison are pure Python — the
model's job stays narrow: structured extraction from one block at a time.
"""
import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from pydantic import BaseModel, ValidationError

from llm import audit
from llm.prompts import (
    extract_clinical_note, extract_discharge, extract_imaging,
    extract_intervention, extract_lab_panel, extract_radiology_impression,
)
from llm.prompts.compare_qualitative import build as build_compare_prompt
from llm.prompts.pre_exam_brief import build as build_pre_exam_brief_prompt
from llm.schemas import ClinicalNoteRecord, ImagingRecord, SCHEMAS, model_extraction_schema
from llm.segment import Block, segment

logger = logging.getLogger(__name__)

PROMPTS = {
    "imaging": extract_imaging,
    "intervention": extract_intervention,
    "clinical_note": extract_clinical_note,
    "radiology_impression": extract_radiology_impression,
    "discharge": extract_discharge,
    "lab_panel": extract_lab_panel,
    # unstructured/unrecognized blocks get a generic clinical-note pass
    "unknown": extract_clinical_note,
}

_EXTRACTION_TIER = "instruct"
_MM_RE = re.compile(r'(\d+(?:\.\d+)?)\s*mm')

# Below this length a phrase is too generic (e.g. "no", "simpla") to be a
# reliable echo signal — only check distinctive multi-word example content.
_ECHO_MIN_PHRASE_LEN = 10


class _ExampleEcho(Exception):
    """Raised when extraction returned the prompt's own few-shot example
    content instead of something derived from the real input — small models
    faced with unfamiliar input (confirmed live: non-English source text)
    can fall back to echoing the example almost verbatim rather than
    generalizing. Treated the same as a validation failure: retry once,
    then flag needs_review rather than silently shipping fabricated data."""


def _example_field_values(prompt_module) -> dict:
    try:
        return json.loads(prompt_module.EXAMPLE_ASSISTANT)
    except (json.JSONDecodeError, AttributeError):
        return {}


def _field_strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


def _is_example_echo(record: BaseModel, prompt_module, block_text: str) -> bool:
    """True if a field's value is essentially the example's value for that
    SAME field, verbatim or near-verbatim — i.e. it can only have come from
    copying the example, not from genuinely reading the input. Compared
    per-field (not any-field-to-any-field) and with a high similarity bar,
    since short generic medical phrasing ("fara complicatii" / "without
    complications") legitimately recurs across unrelated real extractions
    and must not be flagged."""
    example_data = _example_field_values(prompt_module)
    if not example_data:
        return False
    block_lower = block_text.lower()
    record_data = record.model_dump()

    for field_name, example_value in example_data.items():
        if field_name in ("type", "needs_review", "raw_source"):
            continue  # fixed/pipeline-only fields — always match by design, not by echoing
        example_strings = _field_strings(example_value)
        record_strings = _field_strings(record_data.get(field_name))
        for ex, rv in zip(sorted(example_strings), sorted(record_strings)):
            if len(ex) < _ECHO_MIN_PHRASE_LEN:
                continue
            if ex.lower() in block_lower:
                continue  # coincidentally also present in the real input — not an echo
            similarity = SequenceMatcher(None, ex.lower(), rv.lower()).ratio()
            if similarity >= 0.9:
                return True
    return False


def _validate_record(raw: str, schema_cls, prompt_module, block_text: str) -> BaseModel:
    """Raises ValidationError or _ExampleEcho on failure, matching
    extract_block's existing retry-then-needs_review handling for both."""
    record = schema_cls.model_validate_json(raw)
    if _is_example_echo(record, prompt_module, block_text):
        raise _ExampleEcho()
    return record


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
    model_used = router.model_for(_EXTRACTION_TIER) or "unknown"

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
        audit.log_extraction(block.text, _EXTRACTION_TIER, model_used, "needs_review",
                              (time.monotonic() - started) * 1000)
        return schema_cls.model_construct(needs_review=True, raw_source=block.text)

    try:
        record = _validate_record(raw, schema_cls, prompt_module, block.text)
        audit.log_extraction(block.text, _EXTRACTION_TIER, model_used, "ok",
                              (time.monotonic() - started) * 1000)
        return record
    except (ValidationError, _ExampleEcho) as exc:
        if isinstance(exc, _ExampleEcho):
            logger.warning("extraction echoed the prompt's few-shot example, retrying")
        try:
            raw_retry = await router.chat(
                _EXTRACTION_TIER,
                prompt_module.build(block.text, corrective=True),
                json_schema=json_schema,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            logger.warning(f"backend call failed on retry, flagging needs_review: {exc}")
            audit.log_extraction(block.text, _EXTRACTION_TIER, model_used, "needs_review",
                                  (time.monotonic() - started) * 1000)
            return schema_cls.model_construct(needs_review=True, raw_source=block.text)
        try:
            record = _validate_record(raw_retry, schema_cls, prompt_module, block.text)
            audit.log_extraction(block.text, _EXTRACTION_TIER, model_used, "retried",
                                  (time.monotonic() - started) * 1000)
            return record
        except (ValidationError, _ExampleEcho):
            audit.log_extraction(block.text, _EXTRACTION_TIER, model_used, "needs_review",
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


async def extract_typed_blocks(blocks: list[Block], router) -> ExtractionResult:
    """Extract from blocks whose hint_type is already known (e.g. an
    imaging study report fetched from its own API endpoint) — no
    segmentation heuristics involved, since there's nothing to guess."""
    records = list(await asyncio.gather(*(extract_block(b, router) for b in blocks)))
    timeline = assemble_timeline(records)
    return ExtractionResult(records=records, timeline=timeline)


async def extract_document(document: str, router) -> ExtractionResult:
    """Segment a raw document (structural cues + fallback splitting) and
    extract from it — for callers with no independent source of block
    types, e.g. the CLI working on a plain text file."""
    return await extract_typed_blocks(segment(document), router)


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


async def summarize_document(text: str, router, tier: str = "instruct", max_tokens: int = 220) -> str:
    """Rapid orientation brief over the WHOLE raw source text — deliberately
    the opposite of narrate_brief()'s contract. No JSON schema/grammar (free
    prose, no rigid shape to constrain) and therefore no per-field
    validation of the result the way extract_block() gets — this trades the
    schema-validated/echo-checked trust guarantee for the ability to read
    the full document in one pass. Callers must present this as an
    unverified AI aid, not a validated result, distinct from the
    schema-checked extraction records."""
    messages = build_pre_exam_brief_prompt(text)
    return await router.chat(tier, messages, max_tokens=max_tokens, temperature=0.2)
