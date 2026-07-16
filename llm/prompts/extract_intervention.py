from llm.prompts.common import build_messages

SYSTEM = """You extract structured data from one clinical intervention note. \
You do not summarize, interpret, or add information. \
Always respond in English, regardless of the input language — translate \
extracted values into English rather than copying them verbatim. If a \
field is not stated, use null. \
Never include patient names or ID numbers in the output. \
The example below is illustrative only — never repeat its wording; extract \
only what is actually present in the input you are given."""

# Input is Romanian, matching real Hipocrate report text; the example output
# is deliberately translated to English (see extract_imaging.py for why an
# English-only input example caused literal echoing on Romanian input).
EXAMPLE_USER = ("INTERVENTIE CHIRURGICALA in data de 12.03.2026. Diagnostic: "
                 "Apendicita acuta. Interventie: Apendicectomie laparoscopica. "
                 "Evolutie post-operatorie: simpla, fara complicatii.")
EXAMPLE_ASSISTANT = ('{"type":"intervention","date":"2026-03-12",'
                      '"procedure":"laparoscopic appendectomy",'
                      '"outcome":"uncomplicated postoperative course"}')


def build(text: str, corrective: bool = False) -> list[dict]:
    return build_messages(SYSTEM, EXAMPLE_USER, EXAMPLE_ASSISTANT, text, corrective)
