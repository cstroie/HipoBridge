import unittest

from llm.segment import segment


class TestSegmentation(unittest.TestCase):
    def test_segment_structural_headers(self):
        doc = (
            "### CT Scan · 2026-03-02\nHead CT stable.\n\n"
            "### Interventie chirurgicala · 2026-03-05\nAppendectomy performed.\n"
        )
        blocks = segment(doc)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].hint_type, "imaging")
        self.assertEqual(blocks[1].hint_type, "intervention")

    def test_segment_paragraph_fallback(self):
        doc = "First paragraph about admission.\n\nSecond paragraph about discharge."
        blocks = segment(doc)
        self.assertEqual(len(blocks), 2)

    def test_segment_sentence_window_fallback(self):
        doc = "One sentence. Two sentence. Three sentence."
        blocks = segment(doc)
        self.assertGreaterEqual(len(blocks), 1)

    def test_segment_empty_document(self):
        self.assertEqual(segment(""), [])


if __name__ == "__main__":
    unittest.main()
