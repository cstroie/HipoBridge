import json
import unittest

from llm.pipeline import _is_example_echo, assemble_timeline, extract_block, extract_document, extract_typed_blocks
from llm.prompts import extract_imaging, extract_intervention
from llm.router import TierRouter
from llm.schemas import ImagingRecord, InterventionRecord
from llm.segment import Block
from tests.llm_async_helper import run_async


class _FakeBackend:
    def __init__(self, responses):
        self._responses = list(responses)

    async def health(self):
        return True

    async def chat(self, tier, messages, *, json_schema=None, max_tokens=512, temperature=0.0):
        return self._responses.pop(0)


class TestPipelineRetryAndNeedsReview(unittest.TestCase):
    def test_successful_extraction_no_retry(self):
        payload = json.dumps({"type": "clinical_note", "date": None, "summary": "ok"})
        router = TierRouter(_FakeBackend([payload]), {"instruct": "instruct-model"})
        block = Block(text="some note", hint_type="clinical_note", source_offset=(0, 9))
        record = run_async(extract_block(block, router))
        self.assertFalse(record.needs_review)
        self.assertEqual(record.summary, "ok")

    def test_retry_then_success(self):
        good = json.dumps({"type": "clinical_note", "date": None, "summary": "ok"})
        router = TierRouter(_FakeBackend(["not json", good]), {"instruct": "instruct-model"})
        block = Block(text="some note", hint_type="clinical_note", source_offset=(0, 9))
        record = run_async(extract_block(block, router))
        self.assertFalse(record.needs_review)

    def test_double_failure_flags_needs_review(self):
        router = TierRouter(_FakeBackend(["not json", "still not json"]), {"instruct": "instruct-model"})
        block = Block(text="some note", hint_type="clinical_note", source_offset=(0, 9))
        record = run_async(extract_block(block, router))
        self.assertTrue(record.needs_review)
        self.assertEqual(record.raw_source, "some note")

    def test_backend_exception_flags_needs_review_without_raising(self):
        class _ExplodingBackend:
            async def health(self):
                return True

            async def chat(self, *a, **kw):
                raise ConnectionError("server unreachable")

        router = TierRouter(_ExplodingBackend(), {"instruct": "instruct-model"})
        block = Block(text="some note", hint_type="clinical_note", source_offset=(0, 9))
        record = run_async(extract_block(block, router))
        self.assertTrue(record.needs_review)
        self.assertEqual(record.raw_source, "some note")

    def test_unknown_hint_uses_clinical_note_schema(self):
        payload = json.dumps({"type": "clinical_note", "date": None, "summary": "generic"})
        router = TierRouter(_FakeBackend([payload]), {"instruct": "instruct-model"})
        block = Block(text="unstructured text", hint_type="unknown", source_offset=(0, 10))
        record = run_async(extract_block(block, router))
        self.assertEqual(record.type, "clinical_note")

    def test_example_echo_flags_needs_review_instead_of_shipping_fabricated_data(self):
        # Confirmed live: faced with unfamiliar (non-English) input, a small
        # model can fall back to echoing the prompt's own few-shot example
        # almost verbatim rather than extracting real content. Both the
        # first attempt and the retry return the example's exact wording —
        # extract_block must never ship that as a successful extraction.
        echoed_payload = extract_intervention.EXAMPLE_ASSISTANT
        router = TierRouter(_FakeBackend([echoed_payload, echoed_payload]),
                             {"instruct": "instruct-model"})
        block = Block(text="INTERVENTIE CHIRURGICALA in data de 01.01.2026. Text complet diferit.",
                      hint_type="intervention", source_offset=(0, 10))
        record = run_async(extract_block(block, router))
        self.assertTrue(record.needs_review)


class TestExtractTypedBlocks(unittest.TestCase):
    def test_pre_typed_blocks_skip_segmentation(self):
        # A block whose hint_type is already known (e.g. an imaging study
        # fetched from its own API endpoint) must be extracted with that
        # exact type — no re-guessing from segment.py.
        payload = json.dumps({"type": "imaging", "date": "2026-01-01", "modality": "MRI",
                               "body_region": "spine", "findings": [], "impression": None})
        router = TierRouter(_FakeBackend([payload]), {"instruct": "instruct-model"})
        blocks = [Block(text="some ambiguous text with no header at all",
                         hint_type="imaging", source_offset=(0, 10))]
        result = run_async(extract_typed_blocks(blocks, router))
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].type, "imaging")

    def test_mixes_typed_and_segmented_blocks(self):
        imaging_payload = json.dumps({"type": "imaging", "date": "2026-01-01", "modality": "CT",
                                       "body_region": "head", "findings": [], "impression": None})
        note_payload = json.dumps({"type": "clinical_note", "date": None, "summary": "ok"})
        router = TierRouter(_FakeBackend([imaging_payload, note_payload]),
                             {"instruct": "instruct-model"})
        typed = [Block(text="pre-typed imaging report text here", hint_type="imaging",
                        source_offset=(0, 10))]
        from llm.segment import segment
        narrative_blocks = segment("Patient presented with fever and was discharged after treatment.")
        result = run_async(extract_typed_blocks(typed + narrative_blocks, router))
        types = {r.type for r in result.records}
        self.assertIn("imaging", types)


class TestExampleEchoDetection(unittest.TestCase):
    def test_verbatim_echo_detected(self):
        echoed = InterventionRecord.model_validate_json(extract_intervention.EXAMPLE_ASSISTANT)
        block_text = "INTERVENTIE CHIRURGICALA 1 in data de 30.06.2026. Ablatie cateter peritoneal."
        self.assertTrue(_is_example_echo(echoed, extract_intervention, block_text))

    def test_genuine_extraction_not_flagged(self):
        real = InterventionRecord.model_validate_json(
            '{"type":"intervention","date":"2026-06-30",'
            '"procedure":"ablatie cateter peritoneal si neuroendoscopie",'
            '"outcome":"evolutie simpla"}'
        )
        block_text = "INTERVENTIE CHIRURGICALA 1 in data de 30.06.2026. Ablatie cateter peritoneal si neuroendoscopie."
        self.assertFalse(_is_example_echo(real, extract_intervention, block_text))

    def test_shared_type_field_never_flagged(self):
        # Every ImagingRecord shares type="imaging" with the example by
        # design — that must never itself count as an echo.
        real = ImagingRecord.model_validate_json(
            '{"type":"imaging","date":"2026-01-01","modality":"MRI",'
            '"body_region":"spine","findings":["disc herniation L4-L5"],"impression":null}'
        )
        self.assertFalse(_is_example_echo(real, extract_imaging, "MRI spine showing disc herniation L4-L5"))

    def test_phrase_also_present_in_source_not_flagged(self):
        # If the example's phrase genuinely also appears in the real input,
        # it's not an echo — it's a coincidental (or copied-from-source)
        # real match. Only the "findings" field coincides with the example
        # here; every other field is grounded in block_text so they don't
        # also look like echoes for unrelated reasons.
        example_data = json.loads(extract_imaging.EXAMPLE_ASSISTANT)
        matching_finding = example_data["findings"][0]
        record = ImagingRecord.model_validate_json(json.dumps({
            "type": "imaging", "date": "2026-05-01", "modality": "MRI",
            "body_region": "spine", "findings": [matching_finding], "impression": None,
        }))
        block_text = f"MRI spine 2026-05-01. Findings: {matching_finding}."
        self.assertFalse(_is_example_echo(record, extract_imaging, block_text))


class TestAssembleTimeline(unittest.TestCase):
    def test_sorts_by_date_and_marks_undated_unordered(self):
        r1 = ImagingRecord.model_validate_json(
            '{"type":"imaging","date":"2026-04-01","modality":"CT","findings":[]}'
        )
        r2 = ImagingRecord.model_validate_json(
            '{"type":"imaging","date":"2026-03-01","modality":"CT","findings":[]}'
        )
        r3 = ImagingRecord.model_validate_json('{"type":"imaging","date":null,"modality":"CT","findings":[]}')
        entries = assemble_timeline([r1, r2, r3])
        self.assertEqual([e.date for e in entries[:2]], sorted([r1.date, r2.date]))
        self.assertFalse(entries[-1].ordered)

    def test_numeric_delta_between_imaging_records(self):
        earlier = ImagingRecord.model_validate_json(
            '{"type":"imaging","date":"2026-03-01","findings":["5mm lesion"]}'
        )
        later = ImagingRecord.model_validate_json(
            '{"type":"imaging","date":"2026-04-01","findings":["8mm lesion"]}'
        )
        entries = assemble_timeline([earlier, later])
        self.assertIsNone(entries[0].delta_note)
        self.assertIn("+3.0mm", entries[1].delta_note)


if __name__ == "__main__":
    unittest.main()
