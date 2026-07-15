from llm.prompts.common import build_messages

SYSTEM = """You extract structured data from one clinical intervention note. \
You do not summarize, interpret, or add information. \
Copy values exactly as written. If a field is not stated, use null. \
Never include patient names or ID numbers in the output."""

EXAMPLE_USER = ("Interventie chirurgicala · 2026-03-05. Laparoscopic appendectomy "
                "performed without complications.")
EXAMPLE_ASSISTANT = ('{"type":"intervention","date":"2026-03-05",'
                      '"procedure":"laparoscopic appendectomy","outcome":"without complications"}')


def build(text: str, corrective: bool = False) -> list[dict]:
    return build_messages(SYSTEM, EXAMPLE_USER, EXAMPLE_ASSISTANT, text, corrective)
