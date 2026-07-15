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
        doc = ("First paragraph describing the patient's admission course in detail.\n\n"
               "Second paragraph describing the patient's discharge course in detail.")
        blocks = segment(doc)
        self.assertEqual(len(blocks), 2)

    def test_segment_sentence_window_fallback(self):
        doc = "One sentence. Two sentence. Three sentence."
        blocks = segment(doc)
        self.assertGreaterEqual(len(blocks), 1)

    def test_segment_empty_document(self):
        self.assertEqual(segment(""), [])

    def test_segment_skips_patient_demographics_section(self):
        # Real HippoBridge report markdown puts name/age/CNP under "## Patient" —
        # must never reach an extraction prompt (PII leakage + causes small
        # models to hallucinate when given nothing genuinely clinical).
        doc = (
            "## Patient\n\n**Name:** Jane Doe  \n**CNP:** 1234567890123  \n\n"
            "## Admission\n\n_2026-06-27 to 2026-07-14_\n\n"
            "Patient admitted for chest pain. ECG showed normal sinus rhythm. Troponin negative.\n"
        )
        blocks = segment(doc)
        self.assertTrue(all("Jane Doe" not in b.text and "1234567890123" not in b.text for b in blocks))
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].hint_type, "clinical_note")

    def test_segment_skips_header_only_block(self):
        # A lone title header immediately followed by the next header has
        # no real content — never worth an LLM call, guarantees a
        # needs_review false positive if sent.
        doc = "# PATIENT CLINICAL REPORT\n\n## Admission\n\nPatient admitted for chest pain, discharged same day after full workup.\n"
        blocks = segment(doc)
        self.assertEqual(len(blocks), 1)
        self.assertNotIn("PATIENT CLINICAL REPORT", blocks[0].text)

    def test_segment_classifies_real_report_headers(self):
        # "Recent Imaging" / "Clinical History" wording as actually produced
        # by static/scripts.js's report assembly, not the shorter synthetic
        # headers used in the structural-headers test above.
        doc = (
            "## Clinical History\n\n- Total presentations: 8\n- Admissions: 7\n- Discharges: 6\n\n"
            "### CT (5)  ·  2026-03-02  #12345\n\nFollow-up head CT. Ventricle size stable. No new hemorrhage.\n"
        )
        blocks = segment(doc)
        types = {b.hint_type for b in blocks}
        self.assertIn("clinical_note", types)
        self.assertIn("imaging", types)

    def test_segment_splits_inline_intervention_markers(self):
        # Real Hipocrate narrative embeds distinct clinical events as inline
        # uppercase labels, not Markdown headers — confirmed live: without
        # this, an entire admission note (two surgeries + a CT scan) collapsed
        # into one oversized block sent to the clinical_note-only schema,
        # which is what was causing the model to echo the few-shot example
        # instead of extracting real content.
        doc = (
            "## Last Admission\n\n"
            "Patient known with hydrocephalus presented with repeated vomiting episodes "
            "suggesting shunt malfunction requiring urgent evaluation.\n\n"
            "A CT scan performed showed ventricular dilation compared to the prior exam "
            "with evidence of cysts at the left lateral horn requiring surgical review.\n\n"
            "INTERVENTIE CHIRURGICALA 1 in data de 30.06.2026. - Dr. Smith\n\n"
            "Diagnostic: Hydrocephalus. Shunt malfunction\n\n"
            "Interventie: Peritoneal catheter removal and neuroendoscopy with cyst fenestration\n\n"
            "INTERVENTIE CHIRURGICALA 2 in data de 09.07.2026 - Dr. Smith\n\n"
            "Diagnostic: Internal hydrocephalus\n\n"
            "Interventie: Ventriculo-peritoneal shunt placement performed without complications\n"
        )
        blocks = segment(doc)
        types = [b.hint_type for b in blocks]
        self.assertIn("imaging", types)
        self.assertGreaterEqual(types.count("intervention"), 2)
        self.assertTrue(all(len(b.text) < 900 for b in blocks))

    def test_segment_matches_diacritic_and_plain_romanian(self):
        # "INTERVENȚIE" (real diacritic) must classify the same as
        # "interventie" (plain ASCII, also seen in real data) — Hipocrate
        # text mixes both spellings inconsistently.
        diacritic_doc = "INTERVENȚIE CHIRURGICALĂ 1 in data de 01.01.2026.\n\nProcedura a decurs fara incidente, pacientul fiind externat a doua zi.\n"
        plain_doc = "INTERVENTIE CHIRURGICALA 1 in data de 01.01.2026.\n\nProcedura a decurs fara incidente, pacientul fiind externat a doua zi.\n"
        self.assertEqual(segment(diacritic_doc)[0].hint_type, "intervention")
        self.assertEqual(segment(plain_doc)[0].hint_type, "intervention")


if __name__ == "__main__":
    unittest.main()
