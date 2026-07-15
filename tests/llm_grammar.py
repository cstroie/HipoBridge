import unittest

from llm.grammar import to_gbnf, validate_gbnf
from llm.schemas import ClinicalNoteRecord, ImagingRecord, InterventionRecord, model_extraction_schema


class TestGrammarConversion(unittest.TestCase):
    def test_to_gbnf_produces_root_rule(self):
        for cls in (ImagingRecord, InterventionRecord, ClinicalNoteRecord):
            grammar = to_gbnf(model_extraction_schema(cls))
            self.assertIn("root ::=", grammar)
            self.assertIn('"{" ws', grammar)

    def test_to_gbnf_is_structurally_valid(self):
        # No llama.cpp available in this environment to cross-check against
        # the real GBNF parser — this validates every referenced rule is
        # defined and literals/brackets balance, catching the class of bugs
        # a hand-rolled generator is prone to.
        for cls in (ImagingRecord, InterventionRecord, ClinicalNoteRecord):
            grammar = to_gbnf(model_extraction_schema(cls))
            validate_gbnf(grammar)  # raises ValueError on structural defects

    def test_to_gbnf_const_field(self):
        # The GBNF literal must match the JSON-quoted text `"imaging"`, not
        # the bare word `imaging` — json.dumps() alone isn't a GBNF literal,
        # its quotes get consumed as GBNF's own delimiters (see
        # llm/grammar.py's _gbnf_literal docstring for why this matters).
        grammar = to_gbnf(model_extraction_schema(ImagingRecord))
        self.assertIn('root-type ::= "\\"imaging\\""', grammar)

    def test_to_gbnf_nullable_field(self):
        grammar = to_gbnf(model_extraction_schema(ImagingRecord))
        self.assertIn("root-modality ::= string | null", grammar)

    def test_to_gbnf_array_field(self):
        grammar = to_gbnf(model_extraction_schema(ImagingRecord))
        self.assertIn('root-findings ::= "[" ws', grammar)

    def test_to_gbnf_excludes_pipeline_only_fields(self):
        schema = model_extraction_schema(ImagingRecord)
        self.assertNotIn("needs_review", schema["properties"])
        self.assertNotIn("raw_source", schema["properties"])

    def test_to_gbnf_rule_names_never_contain_underscore(self):
        # Confirmed against a real llama-server build: a GBNF rule
        # *identifier* containing '_' makes that rule silently fail to
        # apply, degrading the whole grammar to unconstrained generation
        # with no error surfaced. Field names like `body_region` are
        # common in our schemas, so this must stay sanitized in generated
        # rule names — the JSON key/value *content* is unaffected and
        # still allowed to contain underscores freely.
        grammar = to_gbnf(model_extraction_schema(ImagingRecord))
        for line in grammar.splitlines():
            rule_name = line.split("::=", 1)[0].strip()
            self.assertNotIn("_", rule_name)
        self.assertIn('"\\"body_region\\""', grammar)


if __name__ == "__main__":
    unittest.main()
