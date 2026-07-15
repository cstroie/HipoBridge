from llm.prompts.common import build_messages

SYSTEM = """You extract structured data from one clinical note. \
You do not summarize, interpret, or add information. \
Copy values exactly as written, in the same language as the input — never \
translate. If a field is not stated, use null. \
Never include patient names or ID numbers in the output. \
The example below is illustrative only — never repeat its wording; extract \
only what is actually present in the input you are given."""

# Romanian, matching real Hipocrate report text (see extract_imaging.py for
# why an English-only example caused literal echoing on Romanian input).
EXAMPLE_USER = ("Pacient internat pentru dureri abdominale. Examen clinic: abdomen "
                 "suplu, sensibil in fosa iliaca dreapta. Se externeaza dupa 2 zile "
                 "cu stare generala buna.")
EXAMPLE_ASSISTANT = ('{"type":"clinical_note","date":null,'
                      '"summary":"dureri abdominale, sensibilitate in fosa iliaca dreapta, '
                      'externat dupa 2 zile cu stare buna"}')


def build(text: str, corrective: bool = False) -> list[dict]:
    return build_messages(SYSTEM, EXAMPLE_USER, EXAMPLE_ASSISTANT, text, corrective)
