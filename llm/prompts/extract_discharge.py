from llm.prompts.common import build_messages

SYSTEM = """You are a clinical scribe. Read the discharge letter (scrisoare \
medicala / epicriza) below, which mixes admission history, hospital course, \
and home instructions in no fixed order, and produce a clean structured \
summary. \
executive_summary must be 2-3 sentences covering why the patient was \
admitted and the hospital course. \
Always respond in English, regardless of the input language — translate \
extracted values into English rather than copying them verbatim. \
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
EXAMPLE_ASSISTANT = ('{"type":"discharge","date":null,"executive_summary":"patient admitted '
                      'for acute appendicitis, treated with laparoscopic appendectomy, '
                      'uncomplicated postoperative course",'
                      '"discharge_diagnoses":["operated acute appendicitis"],'
                      '"home_medications":[{"drug_name":"Augmentin","dosage":"1g",'
                      '"frequency":"2 tablets per day, 5 days"}],'
                      '"follow_up_instructions":"surgical follow-up in 2 weeks, avoid '
                      'physical exertion"}')


def build(text: str, corrective: bool = False) -> list[dict]:
    return build_messages(SYSTEM, EXAMPLE_USER, EXAMPLE_ASSISTANT, text, corrective)
