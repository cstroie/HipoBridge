from llm.prompts.common import build_messages

SYSTEM = """You extract structured data from one clinical note. \
You do not summarize, interpret, or add information. \
Copy values exactly as written. If a field is not stated, use null. \
Never include patient names or ID numbers in the output."""

EXAMPLE_USER = ("Patient admitted for chest pain. ECG showed normal sinus rhythm. "
                "Troponin negative. Discharged same day.")
EXAMPLE_ASSISTANT = ('{"type":"clinical_note","date":null,'
                      '"summary":"chest pain, normal ECG, negative troponin, discharged same day"}')


def build(text: str, corrective: bool = False) -> list[dict]:
    return build_messages(SYSTEM, EXAMPLE_USER, EXAMPLE_ASSISTANT, text, corrective)
