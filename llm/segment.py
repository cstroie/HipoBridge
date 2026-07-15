"""Deterministic text segmentation — pure Python, no LLM involved.

Splits a source document into blocks the extractor handles one at a time.
Structural cues (Markdown headers, inline clinical-event markers) are tried
first; a sentence-window splitter with overlap is the fallback for
unstructured text.
"""
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

HintType = Literal["imaging", "intervention", "clinical_note", "unknown"]

# Matches headers like "### CT Scan · 2026-03-02 · id 123" or "## Interventie chirurgicala"
_HEADER_RE = re.compile(r'^#{1,4}\s*(.+)$', re.MULTILINE)

# Real Hipocrate narrative text embeds distinct clinical events as inline
# uppercase labels rather than Markdown headers — e.g. "INTERVENȚIE
# CHIRURGICALA 1 in data de 30.06.2026." mid-paragraph inside one long
# admission note. Without treating these as block boundaries too, an entire
# admission's narrative (multiple surgeries, imaging, evolution notes)
# collapses into one oversized block sent to a single clinical_note schema
# — confirmed live: this is what was causing the model to effectively give
# up and echo the extraction prompt's own few-shot example instead of
# extracting real content.
_EVENT_MARKER_RE = re.compile(
    r'^(INTERVEN[ȚT]IE\s+CHIRURGICAL[AĂ]\s*\d*|SURGICAL\s+INTERVENTION\s*\d*)\b.*$',
    re.IGNORECASE | re.MULTILINE,
)

_HINT_KEYWORDS: dict[HintType, tuple[str, ...]] = {
    "imaging": ("ct scan", "ct ", "ct cerebral", "examen ct", "mri", "rmn", "x-ray",
                "radiograf", "ecograf", "ultrasound", "imaging", "imagist",
                "imagistic", "computer tomograf"),
    "intervention": ("interventie", "intervention", "procedur", "operatie",
                      "surgery", "biopsi", "chirurgical"),
    "clinical_note": ("consult", "nota clinica", "clinical note", "clinical history",
                       "prezentare", "admission", "internare", "externare", "discharge"),
}

# Section headers that are pure demographics/identifiers, never clinical
# narrative — must never reach an extraction prompt. Confirmed against
# HippoBridge's real assembled report markdown ("## Patient" holds name,
# age, sex, DOB, CNP): sending this to the clinical_note extractor leaks
# patient identifiers into the prompt for no benefit, and a small model
# with nothing genuinely clinical to extract tends to regurgitate the
# extraction prompt's own few-shot example almost verbatim instead.
_SKIP_SECTION_TITLES = {"patient"}

# A header line with no real body beneath it (e.g. a lone top-level title
# immediately followed by the next header) is pure noise — never worth an
# LLM call, and guarantees a needs_review false positive.
_MIN_BODY_WORDS = 5

# A block this large (chars) almost certainly bundles multiple distinct
# clinical events even after header/marker splitting — force a further
# paragraph-level split rather than sending one overwhelming blob to a
# single-shape extraction schema.
_MAX_BLOCK_CHARS = 900

_SENTENCE_WINDOW_SIZE = 4       # sentences per block, fallback path
_SENTENCE_WINDOW_OVERLAP = 1    # sentences shared between consecutive blocks


@dataclass
class Block:
    text: str
    hint_type: HintType
    source_offset: tuple[int, int]


def _strip_diacritics(text: str) -> str:
    """Romanian text in real Hipocrate records mixes diacritic and
    non-diacritic spelling ("INTERVENȚIE" vs "interventie") — normalize
    before keyword matching so both spellings hit the same keyword."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _classify_text(text: str, scan_chars: int = 250) -> HintType:
    """Classify by scanning the block's own leading content, not just a
    Markdown header line — a vague header ("## Admission") can sit above a
    body that clearly signals imaging/intervention content."""
    lowered = _strip_diacritics(text[:scan_chars].lower())
    for hint, keywords in _HINT_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return hint
    return "unknown"


def _split_points(document: str) -> list[re.Match]:
    matches = list(_HEADER_RE.finditer(document)) + list(_EVENT_MARKER_RE.finditer(document))
    matches.sort(key=lambda m: m.start())
    return matches


def _segment_by_headers(document: str) -> list[Block] | None:
    matches = _split_points(document)
    if not matches:
        return None

    blocks = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(document)
        text = document[start:end].strip()
        if not text:
            continue

        header_title = match.group(1).strip().lower()
        if header_title in _SKIP_SECTION_TITLES:
            continue

        body = text[match.end() - start:].strip()
        if len(body.split()) < _MIN_BODY_WORDS:
            continue

        blocks.append(Block(text=text, hint_type=_classify_text(text), source_offset=(start, end)))

    if not blocks:
        return None
    return _split_oversized(blocks)


def _split_oversized(blocks: list[Block]) -> list[Block]:
    """Any block still over _MAX_BLOCK_CHARS after header/marker splitting
    almost certainly bundles more than one clinical event — fall back to
    paragraph splitting for that block specifically, each paragraph
    reclassified independently rather than inheriting the parent's hint."""
    result = []
    for block in blocks:
        if len(block.text) <= _MAX_BLOCK_CHARS:
            result.append(block)
            continue
        sub_blocks = _segment_by_paragraphs(block.text)
        if len(sub_blocks) > 1:
            base_start = block.source_offset[0]
            for sub in sub_blocks:
                sub.source_offset = (base_start + sub.source_offset[0], base_start + sub.source_offset[1])
            result.extend(sub_blocks)
        else:
            result.append(block)
    return result


def _segment_by_paragraphs(document: str) -> list[Block]:
    blocks = []
    offset = 0
    for para in re.split(r'\n\s*\n', document):
        stripped = para.strip()
        start = document.index(para, offset) if para else offset
        end = start + len(para)
        offset = end
        if not stripped or len(stripped.split()) < _MIN_BODY_WORDS:
            continue
        blocks.append(Block(text=stripped, hint_type=_classify_text(stripped), source_offset=(start, end)))
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
        blocks.append(Block(text=text, hint_type=_classify_text(text), source_offset=(start, end)))
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
