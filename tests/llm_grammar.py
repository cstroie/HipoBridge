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
        grammar = to_gbnf(model_extraction_schema(ImagingRecord))
        self.assertIn('root-type ::= "imaging"', grammar)

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


if __name__ == "__main__":
    unittest.main()
