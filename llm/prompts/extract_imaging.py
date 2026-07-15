from llm.prompts.common import build_messages

SYSTEM = """You extract structured data from one clinical imaging note. \
You do not summarize, interpret, or add information. \
Copy values exactly as written, in the same language as the input — never \
translate. If a field is not stated, use null. \
Never include patient names or ID numbers in the output. \
The example below is illustrative only — never repeat its wording; extract \
only what is actually present in the input you are given."""

# Romanian, matching real Hipocrate report text — an English-only example
# caused the model to echo this example's wording almost verbatim instead
# of extracting real (Romanian) input, confirmed live against actual
# patient reports.
EXAMPLE_USER = ("CT cerebral efectuat in data de 15.02.2026 la Spitalul Municipal. "
                 "Se evidentiaza dilatatie ventriculara moderata, fara semne de "
                 "hemoragie recenta.")
EXAMPLE_ASSISTANT = ('{"type":"imaging","date":"2026-02-15","modality":"CT",'
                      '"body_region":"cerebral","findings":["dilatatie ventriculara moderata"],'
                      '"impression":"fara semne de hemoragie recenta"}')


def build(text: str, corrective: bool = False) -> list[dict]:
    return build_messages(SYSTEM, EXAMPLE_USER, EXAMPLE_ASSISTANT, text, corrective)
