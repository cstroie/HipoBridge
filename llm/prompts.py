"""Prompt registry for the per-item AI buttons.

Each summary "kind" maps to a (tier, task_prompt, max_tokens) triple. Every
kind's prompt is fully self-contained in its own file
(`llm/prompts/<kind>.md`) — role framing, anti-hallucination rules, and
output-format rules specific to that exact task. There is deliberately no
shared generic preamble prepended to every kind.

This is a reversal of an earlier design that *did* prepend a shared
`system.md` (role framing + general rules + language instruction) ahead of
each kind's task prompt. A/B testing that design against this one
(`benchmark_prompt_format.py`, see `docs/llm_benchmark_2026-07-21.md`) showed
it measurably regressed medgemma-4b-it's language-instruction-following on
the short `imaging` kind: with the shared preamble in place it answered in
Romanian; with everything else held constant and only the preamble removed,
it correctly answered in English. Every kind's own file already restates the
anti-hallucination rule in task-specific language anyway (see each .md file),
so the shared version was pure redundancy at a real cost — a small model's
instruction-following budget is limited, and generic framing text competes
with the specific instructions that actually matter for a short task.
Dedicated, tightly-scoped prompts are also fewer tokens to prefill, which
helps latency too.

`summarize()` is the single convenience entry point the endpoint calls — no
schema, no validation, no echo-detection: these are free-text aids the frontend
presents as unverified ("AI-generated — verify against source"), not validated
results.
"""
import collections.abc
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

# kind -> (tier, max_tokens). The task prompt text is loaded from
# prompts/<kind>.md. Add a kind here and drop in a matching, self-contained
# .md file.
PROMPT_META = {
    "report":    ("default", 340),
    "epicrisis": ("default", 420),
    "imaging":   ("medical", 60),
    "lab":       ("medical", 600),
    "pre_exam":  ("medical", 1300),
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


class _PromptRegistry(collections.abc.Mapping):
    """kind -> (tier, task_prompt, max_tokens), transparently re-reading a
    kind's .md file from disk when it changes (mtime) so an edit made while
    the server is running takes effect on the next request, without a
    restart. Templates are still loaded eagerly at construction time so a
    missing/empty file still fails loudly at import, as before."""

    def __init__(self, meta: dict[str, tuple[str, int]]):
        self._meta = meta
        self._cache: dict[str, tuple[float, str]] = {}  # kind -> (mtime, text)
        for kind in meta:
            self[kind]

    def __getitem__(self, kind: str) -> tuple[str, str, int]:
        tier, max_tokens = self._meta[kind]  # KeyError for unknown kind
        path = os.path.join(_TEMPLATE_DIR, f"{kind}.md")
        mtime = os.path.getmtime(path)
        cached = self._cache.get(kind)
        if cached is None or cached[0] != mtime:
            if cached is not None:
                logger.info(f"Prompt template changed on disk, reloading: {path}")
            text = _load_template(kind)
            self._cache[kind] = (mtime, text)
        else:
            text = cached[1]
        return tier, text, max_tokens

    def __iter__(self):
        return iter(self._meta)

    def __len__(self):
        return len(self._meta)


# kind -> (tier, task_prompt, max_tokens)
PROMPTS = _PromptRegistry(PROMPT_META)


# Kinds that aggregate or narrate events across time, where knowing "today"
# helps the model judge recency/ongoing-ness (e.g. pre_exam's "recent course").
# Excludes imaging (single point-in-time report, no timeline) and lab (each
# row is already explicitly timestamped) — those have no use for it and it
# would just be unused prompt weight on already-lean, short-output kinds.
DATE_AWARE_KINDS = frozenset({"report", "epicrisis", "pre_exam"})


def _date_directive(today: str | None = None) -> str:
    today = today or date.today().isoformat()
    return (
        f" Today's date is {today} — for your own orientation only, never "
        f"for the output. Use it only to judge how recent an event is or "
        f"whether a course is still ongoing, and to convert an EXPLICIT "
        f"relative date actually written in the source (e.g. 'yesterday', "
        f"'3 days ago') into a calendar date. Never write today's date "
        f"itself into the output as if it came from the source. Never use "
        f"it to fill in a date for content that has no date reference at "
        f"all in the source, explicit or relative — that content stays "
        f"undated. Never use it to compute, infer, or invent any other "
        f"fact — such as an age — that is not explicitly stated in the "
        f"source."
    )


def _language_directive(language: str) -> str:
    return (
        f" IMPORTANT: Write your entire response in {language}, regardless of "
        f"the language of the source document — translate the content into "
        f"{language} rather than copying phrases verbatim, and never switch "
        f"language mid-response."
    )


# Kinds served by the streaming endpoint (POST /api/ai/summarize/stream).
# Separate from DATE_AWARE_KINDS even though currently overlapping — one is
# about date context, the other about transport; independently editable.
# imaging (40 tokens) is excluded — too short for streaming to buy anything.
# lab (400 tokens) is included — long enough that perceived latency matters.
STREAMING_KINDS = frozenset({"report", "epicrisis", "pre_exam", "lab"})


def _build_messages(client, kind: str, text: str) -> list[dict]:
    """Assemble the (system, user) messages for `kind` — shared by
    summarize() and summarize_stream() so the two never drift apart.

    The system message is the kind's own self-contained task prompt, with
    the optional date directive and the language directive appended in that
    order — both directly after the task prompt, mirroring the position
    that's actually been validated to work (see module docstring); there is
    no shared preamble ahead of it."""
    _tier, task_prompt, _max_tokens = PROMPTS[kind]
    language = getattr(client, "language", "English") or "English"
    # Kind files may reference the concrete language name via a literal
    # "{language}" placeholder (e.g. pre_exam.md's opening sentence) — a
    # targeted replace, not str.format(), so a prompt with unrelated literal
    # braces (none today, but not guaranteed forever) can't break this.
    system_content = task_prompt.replace("{language}", language)
    if kind in DATE_AWARE_KINDS:
        system_content += _date_directive()
    system_content += _language_directive(language)
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": text},
    ]


async def summarize(client, kind: str, text: str) -> str:
    """Run the prompt for `kind` over `text` and return the reply. The output
    language and sampling temperature come from client.language / .temperature
    (configured in llm.cfg). Raises KeyError for an unknown kind (callers
    validate first)."""
    tier, _task_prompt, max_tokens = PROMPTS[kind]
    temperature = getattr(client, "temperature", 0.1)
    reply = await client.chat(
        tier,
        _build_messages(client, kind, text),
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return reply.strip()


async def summarize_stream(client, kind: str, text: str):
    """Streaming counterpart to summarize() — yields text pieces as they
    arrive instead of returning one final string. Only meaningful for
    `kind in STREAMING_KINDS`; callers validate that before calling (mirrors
    summarize(), which likewise assumes a valid, known kind)."""
    tier, _task_prompt, max_tokens = PROMPTS[kind]
    temperature = getattr(client, "temperature", 0.1)
    async for piece in client.chat_stream(
        tier,
        _build_messages(client, kind, text),
        max_tokens=max_tokens,
        temperature=temperature,
    ):
        yield piece
