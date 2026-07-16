from llm.prompts.common import build_messages

SYSTEM = """You are a clinical scribe. Read the discharge letter (scrisoare \
medicala / epicriza) below, which mixes admission history, hospital course, \
and home instructions in no fixed order, and produce a clean structured \
summary. \
executive_summary must be 2-3 sentences covering why the patient was \
admitted and the hospital course. \
Write in the same language as the input — never translate. \
Never invent diagnoses, medications, or instructions not present in the \
source; if a field is not stated, use an empty list or null. \
Never include patient names or ID numbers in the output. \
The example below is illustrative only — never repeat its wording; extract \
only what is actually present in the input you are given."""

EXAMPLE_USER = ("Pacient internat pentru dureri abdominale in fosa iliaca dreapta, "
                 "debut de 2 zile. Diagnostic la internare: apendicita acuta. "
                 "Se practica apendicectomie laparoscopica, evolutie postoperatorie "
                 "simpla. Diagnostic la externare: apendicita acuta operata. "
                 "Tratament la domiciliu: Augmentin 1g, 2 comprimate pe zi, timp de 5 zile. "
                 "Recomandari: control chirurgical peste 2 saptamani, evitarea efortului fizic.")
EXAMPLE_ASSISTANT = ('{"type":"discharge","date":null,"executive_summary":"pacient internat '
                      'pentru apendicita acuta, tratat prin apendicectomie laparoscopica, '
                      'evolutie postoperatorie simpla",'
                      '"discharge_diagnoses":["apendicita acuta operata"],'
                      '"home_medications":[{"drug_name":"Augmentin","dosage":"1g",'
                      '"frequency":"2 comprimate pe zi, 5 zile"}],'
                      '"follow_up_instructions":"control chirurgical peste 2 saptamani, '
                      'evitarea efortului fizic"}')


def build(text: str, corrective: bool = False) -> list[dict]:
    return build_messages(SYSTEM, EXAMPLE_USER, EXAMPLE_ASSISTANT, text, corrective)
