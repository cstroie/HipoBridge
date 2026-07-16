from llm.prompts.common import build_messages

SYSTEM = """You are a senior radiologist. Read the full imaging report below \
and produce a sharp clinical impression. \
The impression field must be a single sentence, under 25 words — the core \
diagnostic conclusion only, not a restatement of every finding. \
Always respond in English, regardless of the input language — translate \
extracted values into English rather than copying them verbatim. \
Never invent findings, dates, or a modality not present in the source; if a \
field is not stated, use null. \
Never include patient names or ID numbers in the output. \
The example below is illustrative only — never repeat its wording; extract \
only what is actually present in the input you are given."""

EXAMPLE_USER = ("CT torace efectuat in data de 03.04.2026. Se descriu multiple opacitati "
                 "nodulare bilaterale, cu dimensiuni intre 4-9mm, distributie predominant "
                 "bazala. Nu se observa adenopatii mediastinale semnificative. Nu exista "
                 "revarsat pleural.")
EXAMPLE_ASSISTANT = ('{"type":"radiology_impression","date":"2026-04-03","modality":"CT",'
                      '"body_region":"chest","impression":"bilateral basal nodular '
                      'opacities, no significant mediastinal adenopathy",'
                      '"significant_findings":true}')


def build(text: str, corrective: bool = False) -> list[dict]:
    return build_messages(SYSTEM, EXAMPLE_USER, EXAMPLE_ASSISTANT, text, corrective)
