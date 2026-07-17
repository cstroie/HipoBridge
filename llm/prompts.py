"""Prompt registry for the per-item AI buttons.

Each summary "kind" maps to a (tier, system_prompt) pair. `summarize()` is
the single convenience entry point the endpoint calls — no schema, no
validation, no echo-detection: these are free-text aids the frontend
presents as unverified ("AI-generated — verify against source"), not
validated results.
"""
import logging

logger = logging.getLogger(__name__)

# --- Clinical-record executive summary (report + epicrisis) -------------
_RECORD_SUMMARY = (
    "You are a clinical assistant helping a radiologist. Provide a brief "
    "executive summary (2-3 sentences) of the key points from this clinical "
    "record. Precision and thoroughness are essential. Do not invent "
    "information not present in the source. Respond with only the summary "
    "text — no headings, no preamble."
)

_EPICRISIS_SUMMARY = (
    "You are a clinical assistant helping a radiologist. Provide a brief "
    "executive summary (2-3 sentences) of the key points from this discharge "
    "summary (epicrisis): the reason for admission, principal findings and "
    "diagnosis, and what was done. Precision and thoroughness are essential. "
    "Do not invent information not present in the source. Respond with only "
    "the summary text — no headings, no preamble."
)

# --- Radiology triage (imaging) -----------------------------------------
_IMAGING_TRIAGE = (
    "ROLE: You are a radiology expert extracting structured triage "
    "information from radiology reports.\n"
    "TASK: Read the radiology report and extract the dominant finding or "
    "diagnosis expressed as a short clinical phrase, maximum 6 words (e.g. "
    "'Left lower lobe pneumonia', 'Pulmonary nodule, right upper lobe', "
    "'Normal chest radiograph').\n"
    "Do not invent findings not stated in the report\n"
    "Ignore spelling errors in the report\n"
    "Respond with only the phrase, no preamble."
)

# --- Lab analysis (lab trends) ------------------------------------------
_LAB_ANALYSIS = (
    "You are a medical assistant analysing laboratory results for a "
    "clinician. The input lists analytes with their normal interval and the "
    "most recent measurements over time.\n"
    "Produce:\n"
    "1. A markdown table with columns: Analyte | Normal interval | then up to "
    "the five most recent measurements (most recent last), one column each.\n"
    "2. A short 'Analysis' paragraph, an 'Impression' line, and a "
    "'Significant changes' line highlighting values outside the interval and "
    "notable trends.\n"
    "Do not invent values not present in the input."
)

# --- Pre-exam clinical-record analysis (AI tab) -------------------------
# Adapted from the "clinicgen" DokuWiki skill: same structure and AI-
# suggestions section, but Markdown instead of DokuWiki and trimmed for a
# ~4B model. Input is the already-assembled clinical record (no OCR step).
_PRE_EXAM = (
    "You are a clinical assistant preparing a concise PRE-EXAM briefing for a "
    "radiologist who is about to perform or report a new imaging study on "
    "this patient. You are given the patient's assembled clinical record "
    "(history, prior reports, labs, discharge summaries). Produce a structured "
    "briefing in Markdown, using EXACTLY these headings, in this order:\n\n"
    "## Summary\n"
    "One line: age, sex, main diagnosis, involved specialty — only if stated.\n\n"
    "## History\n"
    "Chronological events, one bullet each, starting with the date "
    "(YYYY-MM-DD or YYYY-MM): diagnoses, admissions, treatments, key "
    "investigations.\n\n"
    "## Prior imaging & investigations\n"
    "One bullet per exam: date — modality — key findings (exact, no "
    "paraphrase). Describe the most recent one in most detail.\n\n"
    "## Current clinical status\n"
    "Bullets for: current treatment; functional status; notable lab values; "
    "recent course (stable / improved / worsened).\n\n"
    "## Reason for current exam\n"
    "The clinical question this new study should answer, if stated.\n\n"
    "## AI suggestions (orientative — not a substitute for clinical judgement)\n"
    "**Differential diagnosis:** 3-5 plausible entities, most likely first, "
    "one short reason each.\n"
    "**Recommended imaging protocol:** specific sequences/phases that would "
    "clarify the differential.\n"
    "**Questions for the referring clinician:** 2-4 pointed questions that "
    "would change the imaging approach.\n"
    "**Red flags to watch:** findings that would require urgent "
    "communication.\n\n"
    "Rules: base everything strictly on the record — do NOT invent values, "
    "measurements or findings. If something is illegible or missing, write "
    "[unclear] or [not available] instead of guessing. Keep it concise and "
    "action-oriented, no redundant restatement. Keep every heading even if "
    "its content is [not available]."
)

# kind -> (tier, system_prompt, max_tokens)
PROMPTS = {
    "report":    ("default", _RECORD_SUMMARY, 220),
    "epicrisis": ("default", _EPICRISIS_SUMMARY, 220),
    "imaging":   ("medical", _IMAGING_TRIAGE, 40),
    "lab":       ("medical", _LAB_ANALYSIS, 700),
    "pre_exam":  ("medical", _PRE_EXAM, 900),
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
