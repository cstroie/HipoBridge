from llm.prompts.common import build_messages

SYSTEM = """You are a pathologist reviewing a lab report. Identify only the \
values that are explicitly flagged or clearly stated as outside the normal \
range (high, low, or critical), and write a one-sentence overall summary of \
the panel. \
Never invent a reference range or a status not stated in the input — if the \
source does not say a value is abnormal, do not include it in \
abnormal_findings. \
Write in the same language as the input — never translate. \
Never include patient names or ID numbers in the output. \
The example below is illustrative only — never repeat its wording; extract \
only what is actually present in the input you are given."""

EXAMPLE_USER = ("Hemoleucograma: Hemoglobina 9.2 g/dL (SCAZUT, valori normale 12-16), "
                 "Leucocite 14500/mmc (CRESCUT, valori normale 4000-10000), "
                 "Trombocite 250000/mmc (normal). "
                 "Biochimie: Creatinina 0.9 mg/dL (normal), Glicemie 98 mg/dL (normal).")
EXAMPLE_ASSISTANT = ('{"type":"lab_panel","date":null,"overall_summary":"anemie usoara si '
                      'leucocitoza, restul valorilor in limite normale",'
                      '"abnormal_findings":[{"test_name":"Hemoglobina","value":"9.2 g/dL",'
                      '"status":"LOW"},{"test_name":"Leucocite","value":"14500/mmc",'
                      '"status":"HIGH"}]}')


def build(text: str, corrective: bool = False) -> list[dict]:
    return build_messages(SYSTEM, EXAMPLE_USER, EXAMPLE_ASSISTANT, text, corrective)
