import json
import unittest

from llm.pipeline import assemble_timeline, extract_block, extract_document
from llm.router import TierRouter
from llm.schemas import ImagingRecord
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
        router = TierRouter({"instruct": _FakeBackend([payload])})
        block = Block(text="some note", hint_type="clinical_note", source_offset=(0, 9))
        record = run_async(extract_block(block, router))
        self.assertFalse(record.needs_review)
        self.assertEqual(record.summary, "ok")

    def test_retry_then_success(self):
        good = json.dumps({"type": "clinical_note", "date": None, "summary": "ok"})
        router = TierRouter({"instruct": _FakeBackend(["not json", good])})
        block = Block(text="some note", hint_type="clinical_note", source_offset=(0, 9))
        record = run_async(extract_block(block, router))
        self.assertFalse(record.needs_review)

    def test_double_failure_flags_needs_review(self):
        router = TierRouter({"instruct": _FakeBackend(["not json", "still not json"])})
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

        router = TierRouter({"instruct": _ExplodingBackend()})
        block = Block(text="some note", hint_type="clinical_note", source_offset=(0, 9))
        record = run_async(extract_block(block, router))
        self.assertTrue(record.needs_review)
        self.assertEqual(record.raw_source, "some note")

    def test_unknown_hint_uses_clinical_note_schema(self):
        payload = json.dumps({"type": "clinical_note", "date": None, "summary": "generic"})
        router = TierRouter({"instruct": _FakeBackend([payload])})
        block = Block(text="unstructured text", hint_type="unknown", source_offset=(0, 10))
        record = run_async(extract_block(block, router))
        self.assertEqual(record.type, "clinical_note")


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
