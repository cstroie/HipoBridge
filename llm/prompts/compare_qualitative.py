"""THINKING-tier helper: qualitative comparison between two structured
imaging records, used only when a pure-Python numeric diff can't decide
(see llm/pipeline.py's assemble_timeline). Feeds structured records only,
never raw source text; output is capped to a single word."""

SYSTEM = """You compare two structured imaging records from the same patient, \
ordered earliest first. Answer with exactly one word: "stable", "improved", \
or "progressed". Do not explain your reasoning in the output."""


def build(earlier: dict, later: dict) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Earlier: {earlier}\nLater: {later}"},
    ]
