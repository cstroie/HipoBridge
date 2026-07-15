from llm.prompts.common import build_messages

SYSTEM = """You extract structured data from one clinical intervention note. \
You do not summarize, interpret, or add information. \
Copy values exactly as written, in the same language as the input — never \
translate. If a field is not stated, use null. \
Never include patient names or ID numbers in the output. \
The example below is illustrative only — never repeat its wording; extract \
only what is actually present in the input you are given."""

# Romanian, matching real Hipocrate report text (see extract_imaging.py for
# why an English-only example caused literal echoing on Romanian input).
EXAMPLE_USER = ("INTERVENTIE CHIRURGICALA in data de 12.03.2026. Diagnostic: "
                 "Apendicita acuta. Interventie: Apendicectomie laparoscopica. "
                 "Evolutie post-operatorie: simpla, fara complicatii.")
EXAMPLE_ASSISTANT = ('{"type":"intervention","date":"2026-03-12",'
                      '"procedure":"apendicectomie laparoscopica",'
                      '"outcome":"evolutie simpla, fara complicatii"}')


def build(text: str, corrective: bool = False) -> list[dict]:
    return build_messages(SYSTEM, EXAMPLE_USER, EXAMPLE_ASSISTANT, text, corrective)
