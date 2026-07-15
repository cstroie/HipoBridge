"""Free-text summarization over a whole report — deliberately the opposite
contract from the other prompts/ modules and from pipeline.py's
narrate_brief(): this one reads raw source text directly, not validated
structured records. No JSON schema/grammar (there's no rigid shape to
constrain natural-language sentences into), and therefore no per-field
validation possible on the result — weaker trust than the schema-validated
extraction records. Callers must surface this as an unverified AI aid, not
a validated result.
"""

SYSTEM = """You are a medical assistant preparing a rapid orientation brief \
for a radiologist who has only a few seconds before performing or reporting \
a new imaging study on this patient. Read the full clinical report below \
and write a 3-5 sentence executive summary covering, in this order: \
(1) who the patient is (age, sex) — only if explicitly stated in the input, \
(2) the core clinical problem, (3) key imaging findings already established, \
(4) interventions performed, (5) the current clinical question this new \
exam should help answer. \
Write in the same language as the source document — never translate, and \
never switch language mid-sentence. \
Do not invent information not present in the source, including age, sex, \
or dates — if a point has no information in the source, omit it entirely \
rather than guessing. \
Respond with only the summary text, no headings, no preamble."""


def build(text: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": text},
    ]
