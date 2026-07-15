"""Deterministic text segmentation — pure Python, no LLM involved.

Splits a source document into blocks the extractor handles one at a time.
Structural cues (headers, blank-line paragraphs) are tried first; a
sentence-window splitter with overlap is the fallback for unstructured text.
"""
import re
from dataclasses import dataclass
from typing import Literal

HintType = Literal["imaging", "intervention", "clinical_note", "unknown"]

# Matches headers like "### CT Scan · 2026-03-02 · id 123" or "## Interventie chirurgicala"
_HEADER_RE = re.compile(r'^#{1,4}\s*(.+)$', re.MULTILINE)

_HINT_KEYWORDS: dict[HintType, tuple[str, ...]] = {
    "imaging": ("ct scan", "ct ", "mri", "rmn", "x-ray", "radiograf", "ecograf",
                "ultrasound", "imagist", "computer tomograf"),
    "intervention": ("interventie", "intervention", "procedur", "operatie",
                      "surgery", "biopsi"),
    "clinical_note": ("consult", "nota clinica", "clinical note", "prezentare",
                       "admission", "internare", "externare", "discharge"),
}

_SENTENCE_WINDOW_SIZE = 4       # sentences per block, fallback path
_SENTENCE_WINDOW_OVERLAP = 1    # sentences shared between consecutive blocks


@dataclass
class Block:
    text: str
    hint_type: HintType
    source_offset: tuple[int, int]


def _classify_header(header_text: str) -> HintType:
    lowered = header_text.lower()
    for hint, keywords in _HINT_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return hint
    return "unknown"


def _segment_by_headers(document: str) -> list[Block] | None:
    matches = list(_HEADER_RE.finditer(document))
    if not matches:
        return None

    blocks = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(document)
        text = document[start:end].strip()
        if not text:
            continue
        blocks.append(Block(text=text, hint_type=_classify_header(match.group(1)), source_offset=(start, end)))
    return blocks or None


def _segment_by_paragraphs(document: str) -> list[Block]:
    blocks = []
    offset = 0
    for para in re.split(r'\n\s*\n', document):
        stripped = para.strip()
        start = document.index(para, offset) if para else offset
        end = start + len(para)
        offset = end
        if not stripped:
            continue
        blocks.append(Block(text=stripped, hint_type=_classify_header(stripped[:120]), source_offset=(start, end)))
    return blocks


_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')


def _segment_by_sentence_window(document: str) -> list[Block]:
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(document) if s.strip()]
    if not sentences:
        return []

    blocks = []
    step = max(_SENTENCE_WINDOW_SIZE - _SENTENCE_WINDOW_OVERLAP, 1)
    cursor = 0
    for i in range(0, len(sentences), step):
        window = sentences[i:i + _SENTENCE_WINDOW_SIZE]
        text = " ".join(window).strip()
        if not text:
            continue
        start = document.find(text[:40], cursor) if text else cursor
        start = start if start != -1 else cursor
        end = start + len(text)
        cursor = start
        blocks.append(Block(text=text, hint_type=_classify_header(text[:120]), source_offset=(start, end)))
    return blocks


def segment(document: str) -> list[Block]:
    document = document.strip()
    if not document:
        return []

    header_blocks = _segment_by_headers(document)
    if header_blocks is not None:
        return header_blocks

    paragraph_blocks = _segment_by_paragraphs(document)
    if len(paragraph_blocks) > 1:
        return paragraph_blocks

    return _segment_by_sentence_window(document)
