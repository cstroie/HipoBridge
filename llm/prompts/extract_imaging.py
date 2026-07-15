from llm.prompts.common import build_messages

SYSTEM = """You extract structured data from one clinical imaging note. \
You do not summarize, interpret, or add information. \
Copy values exactly as written. If a field is not stated, use null. \
Never include patient names or ID numbers in the output."""

EXAMPLE_USER = ("CT Scan · 2026-03-02. Follow-up head CT. Ventricle size stable "
                "compared to prior. No new hemorrhage.")
EXAMPLE_ASSISTANT = ('{"type":"imaging","date":"2026-03-02","modality":"CT",'
                      '"body_region":"head","findings":["ventricle size stable",'
                      '"no new hemorrhage"],"impression":null}')


def build(text: str, corrective: bool = False) -> list[dict]:
    return build_messages(SYSTEM, EXAMPLE_USER, EXAMPLE_ASSISTANT, text, corrective)
