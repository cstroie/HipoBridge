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
The source document is written in a specific language — detect it and write \
your ENTIRE response in that same language, with no English at all unless \
the source itself is in English. Do not translate any part of your answer, \
and never switch language mid-sentence. This rule overrides any default \
tendency to answer in English. \
Do not invent information not present in the source, including age, sex, \
or dates — if a point has no information in the source, omit it entirely \
rather than guessing. \
Respond with only the summary text, no headings, no preamble."""

# One-shot demonstration that the reply must stay in the source's language
# (Romanian here, matching real Hipocrate report text) — confirmed live:
# without a concrete example, medgemma-4b-it silently answered in English
# despite the "never translate" instruction above, even though the same
# instruction (paired with a Romanian few-shot example) works reliably in
# the extract_*.py prompts.
EXAMPLE_USER = ("Pacient de 58 de ani, internat pentru dureri abdominale in etajul "
                 "superior, debut de 3 zile. Ecografia abdominala initiala a evidentiat "
                 "calculi biliari multipli. S-a practicat colecistectomie laparoscopica, "
                 "evolutie postoperatorie favorabila.")
EXAMPLE_ASSISTANT = ("Pacient de 58 de ani, internat pentru dureri abdominale in etajul "
                      "superior. Ecografia initiala a evidentiat calculi biliari multipli. "
                      "S-a practicat colecistectomie laparoscopica, cu evolutie "
                      "postoperatorie favorabila. Intrebarea clinica actuala pentru noul "
                      "examen imagistic nu este specificata in sursa.")


def build(text: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": EXAMPLE_USER},
        {"role": "assistant", "content": EXAMPLE_ASSISTANT},
        {"role": "user", "content": text},
    ]
