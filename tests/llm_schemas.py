import unittest

from pydantic import ValidationError

from llm.schemas import ImagingRecord


class TestExtractedRecordValidation(unittest.TestCase):
    def test_valid_imaging_record(self):
        record = ImagingRecord.model_validate_json(
            '{"type":"imaging","date":"2026-03-02","modality":"CT","body_region":"head",'
            '"findings":["stable"],"impression":null}'
        )
        self.assertEqual(record.modality, "CT")
        self.assertFalse(record.needs_review)

    def test_invalid_json_raises(self):
        with self.assertRaises(ValidationError):
            ImagingRecord.model_validate_json("not json")

    def test_model_construct_marks_needs_review(self):
        record = ImagingRecord.model_construct(needs_review=True, raw_source="some raw text")
        self.assertTrue(record.needs_review)
        self.assertEqual(record.raw_source, "some raw text")


if __name__ == "__main__":
    unittest.main()
