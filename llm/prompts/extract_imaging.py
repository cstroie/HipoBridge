from llm.prompts.common import build_messages

SYSTEM = """You extract structured data from one clinical imaging note. \
You do not summarize, interpret, or add information. \
Always respond in English, regardless of the input language — translate \
extracted values into English rather than copying them verbatim. If a \
field is not stated, use null. \
Never include patient names or ID numbers in the output. \
The example below is illustrative only — never repeat its wording; extract \
only what is actually present in the input you are given."""

# Input is Romanian, matching real Hipocrate report text; the example output
# is deliberately translated to English to demonstrate the required output
# language (an English-only input example caused the model to echo the
# example's wording almost verbatim instead of extracting real (Romanian)
# input, confirmed live against actual patient reports).
EXAMPLE_USER = ("CT cerebral efectuat in data de 15.02.2026 la Spitalul Municipal. "
                 "Se evidentiaza dilatatie ventriculara moderata, fara semne de "
                 "hemoragie recenta.")
EXAMPLE_ASSISTANT = ('{"type":"imaging","date":"2026-02-15","modality":"CT",'
                      '"body_region":"cerebral","findings":["moderate ventricular dilation"],'
                      '"impression":"no signs of recent hemorrhage"}')


def build(text: str, corrective: bool = False) -> list[dict]:
    return build_messages(SYSTEM, EXAMPLE_USER, EXAMPLE_ASSISTANT, text, corrective)
