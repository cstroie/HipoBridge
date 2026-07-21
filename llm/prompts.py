"""Prompt registry for the per-item AI buttons.

Each summary "kind" maps to a (tier, task_prompt, max_tokens) triple. The
task prompt text lives as an editable Markdown file in `llm/prompts/<kind>.md`
(one per kind) so prompts can be tuned without touching code; this module
loads them at import and pairs each with its tier + token budget from
`PROMPT_META`.

`llm/prompts/system.md` holds the fixed, non-task-specific instructions
shared by every kind (role framing, output language, anti-fabrication/
no-preamble backstop). Every call's system message is this shared prompt,
plus an optional date directive, plus the kind's task prompt — see
`_build_messages()`.

`summarize()` is the single convenience entry point the endpoint calls — no
schema, no validation, no echo-detection: these are free-text aids the frontend
presents as unverified ("AI-generated — verify against source"), not validated
results.
"""
import logging
import os
import re
from datetime import date

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
_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "prompts")

# kind -> (tier, max_tokens). The system prompt text is loaded from
# prompts/<kind>.md. Add a kind here and drop in a matching .md file.
PROMPT_META = {
    "report":    ("default", 220),
    "epicrisis": ("default", 220),
    "imaging":   ("medical", 40),
    "lab":       ("medical", 400),
    "pre_exam":  ("medical", 900),
}


def _load_template(name: str) -> str:
    """Read a template file by name (without extension) from the prompts
    dir. Fails loudly (at import) if the file is missing or empty — a
    misconfigured prompt should not silently degrade the AI output."""
    path = os.path.join(_TEMPLATE_DIR, f"{name}.md")
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        raise ValueError(f"empty prompt template: {path}")
    return text


# kind -> (tier, system_prompt, max_tokens)
PROMPTS = {
    kind: (tier, _load_template(kind), max_tokens)
    for kind, (tier, max_tokens) in PROMPT_META.items()
}

# Shared system prompt: fixed, non-task-specific instructions (role framing,
# output language, anti-fabrication/no-preamble backstop) that apply to every
# kind. Kept in its own file (prompts/system.md) rather than inlined per-kind
# so the fixed rules are edited once instead of drifting across 5 files.
# Contains a `{language}` placeholder filled in at call time from
# client.language (configured in llm.cfg).
_SYSTEM_TEMPLATE = _load_template("system")


def _system_prompt(language: str) -> str:
    return _SYSTEM_TEMPLATE.format(language=language)


# Kinds that aggregate or narrate events across time, where knowing "today"
# helps the model judge recency/ongoing-ness (e.g. pre_exam's "recent course").
# Excludes imaging (single point-in-time report, no timeline) and lab (each
# row is already explicitly timestamped) — those have no use for it and it
# would just be unused prompt weight on already-lean, short-output kinds.
DATE_AWARE_KINDS = frozenset({"report", "epicrisis", "pre_exam"})


def _date_directive(today: str | None = None) -> str:
    today = today or date.today().isoformat()
    return (
        f" Today's date is {today}. Use this only to judge how recent an "
        f"event is, whether a course is still ongoing, or to resolve an "
        f"explicit relative date in the source (e.g. 'yesterday'). Never use "
        f"it to compute, infer, or invent any fact — such as an age — that "
        f"is not explicitly stated in the source."
    )


# Kinds served by the streaming endpoint (POST /api/ai/summarize/stream).
# Separate from DATE_AWARE_KINDS even though currently the same set — one is
# about date context, the other about transport; independently editable.
# imaging (40 tokens) and lab (already fast, table-free prose) don't benefit
# enough from streaming to justify a second code path for them.
STREAMING_KINDS = frozenset({"report", "epicrisis", "pre_exam"})


def _build_messages(client, kind: str, text: str) -> list[dict]:
    """Assemble the (system, user) messages for `kind` — shared by
    summarize() and summarize_stream() so the two never drift apart.

    The system message is the shared, fixed prompt (role, output language)
    from prompts/system.md, followed by the optional date directive, followed
    by the kind-specific task template — kept as one message (rather than
    separate system-role entries) since local chat templates commonly only
    render a single system message."""
    _tier, task_prompt, _max_tokens = PROMPTS[kind]
    language = getattr(client, "language", "English") or "English"
    system_content = _system_prompt(language)
    if kind in DATE_AWARE_KINDS:
        system_content += _date_directive()
    system_content += "\n\n" + task_prompt
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": text},
    ]


async def summarize(client, kind: str, text: str) -> str:
    """Run the prompt for `kind` over `text` and return the reply. The output
    language comes from client.language (configured in llm.cfg). Raises
    KeyError for an unknown kind (callers validate first)."""
    tier, _system, max_tokens = PROMPTS[kind]
    reply = await client.chat(
        tier,
        _build_messages(client, kind, text),
        max_tokens=max_tokens,
        temperature=0.1,
    )
    return reply.strip()


async def summarize_stream(client, kind: str, text: str):
    """Streaming counterpart to summarize() — yields text pieces as they
    arrive instead of returning one final string. Only meaningful for
    `kind in STREAMING_KINDS`; callers validate that before calling (mirrors
    summarize(), which likewise assumes a valid, known kind)."""
    tier, _system, max_tokens = PROMPTS[kind]
    async for piece in client.chat_stream(
        tier,
        _build_messages(client, kind, text),
        max_tokens=max_tokens,
        temperature=0.1,
    ):
        yield piece
