"""Prompt registry for the per-item AI buttons.

Each summary "kind" maps to a (tier, system_prompt, max_tokens) triple. The
system prompt text lives as an editable Markdown file in
`llm/prompt_templates/<kind>.md` (one per kind) so prompts can be tuned without
touching code; this module loads them at import and pairs each with its tier +
token budget from `PROMPT_META`.

`summarize()` is the single convenience entry point the endpoint calls — no
schema, no validation, no echo-detection: these are free-text aids the frontend
presents as unverified ("AI-generated — verify against source"), not validated
results.
"""
import logging
import os
import re

logger = logging.getLogger(__name__)

# Matches markdown scaffolding (headers, list/emphasis markers, table pipes)
# so has_meaningful_content() can tell "no real content" apart from a
# populated document that merely happens to be short.
_MARKDOWN_SCAFFOLD_RE = re.compile(r'[#*_>`|\-]+')
MIN_MEANINGFUL_CHARS = 15


def has_meaningful_content(text: str, min_chars: int = MIN_MEANINGFUL_CHARS) -> bool:
    """True if `text` has at least `min_chars` of real content once markdown
    scaffolding and whitespace are stripped.

    Guards against calling the model on an effectively empty record (e.g. just
    a "## Report" header with no body) — confirmed live that an ungrounded
    small model will confidently fabricate an entire clinical scenario,
    including demographics, rather than report there is nothing to
    summarize."""
    stripped = _MARKDOWN_SCAFFOLD_RE.sub('', text)
    stripped = re.sub(r'\s+', '', stripped)
    return len(stripped) >= min_chars

# Prompt templates live next to this module so the path is independent of the
# process working directory (mirrors the os.path.dirname(__file__) convention).
_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "prompt_templates")

# kind -> (tier, max_tokens). The system prompt text is loaded from
# prompt_templates/<kind>.md. Add a kind here and drop in a matching .md file.
PROMPT_META = {
    "report":    ("default", 220),
    "epicrisis": ("default", 220),
    "imaging":   ("medical", 40),
    "lab":       ("medical", 400),
    "pre_exam":  ("medical", 900),
}


def _load_prompt(kind: str) -> str:
    """Read the system prompt for `kind` from its template file. Fails loudly
    (at import) if the file is missing or empty — a misconfigured prompt should
    not silently degrade the AI output."""
    path = os.path.join(_TEMPLATE_DIR, f"{kind}.md")
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        raise ValueError(f"empty prompt template: {path}")
    return text


# kind -> (tier, system_prompt, max_tokens)
PROMPTS = {
    kind: (tier, _load_prompt(kind), max_tokens)
    for kind, (tier, max_tokens) in PROMPT_META.items()
}


def _language_directive(language: str) -> str:
    return (
        f" IMPORTANT: Write your entire response in {language}, regardless of "
        f"the language of the source document — translate the content into "
        f"{language} rather than copying phrases verbatim, and never switch "
        f"language mid-sentence."
    )


async def summarize(client, kind: str, text: str) -> str:
    """Run the prompt for `kind` over `text` and return the reply. The output
    language comes from client.language (configured in llm.cfg). Raises
    KeyError for an unknown kind (callers validate first)."""
    tier, system, max_tokens = PROMPTS[kind]
    language = getattr(client, "language", "English") or "English"
    reply = await client.chat(
        tier,
        [
            {"role": "system", "content": system + _language_directive(language)},
            {"role": "user", "content": text},
        ],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return reply.strip()
