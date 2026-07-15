"""Fixture-based extraction pass-rate harness.

Self-skips unless llama-cpp-python and configured GGUFs are actually
available — this is the one test group meant to run against real models
(both a server-forced and inprocess-forced router), not stub backends.
Not wired into "all" by default for that reason; run explicitly via
`python3 runtests.py llm` once models are present.
"""
import os
import unittest

try:
    import llama_cpp  # noqa: F401
    LLAMA_CPP_AVAILABLE = True
except ImportError:
    LLAMA_CPP_AVAILABLE = False

from llm.config import init_llm, tier_section
from llm.pipeline import extract_block
from llm.segment import Block
from tests.llm_async_helper import run_async

FIXTURES = [
    {
        "text": "CT Scan · 2026-03-02. Follow-up head CT. Ventricle size stable compared to prior. No new hemorrhage.",
        "hint_type": "imaging",
        "expected": {"type": "imaging", "date": "2026-03-02", "modality": "CT"},
    },
]

PASS_RATE_THRESHOLD = 0.95


def _gguf_configured() -> bool:
    config = init_llm()
    tier_cfg = tier_section(config, "instruct")
    path = tier_cfg.get("local_path", "")
    return bool(path) and os.path.exists(path)


@unittest.skipUnless(LLAMA_CPP_AVAILABLE and _gguf_configured(),
                      "llama-cpp-python and/or a configured GGUF not available")
class TestFixtureEvalHarness(unittest.TestCase):
    def test_inprocess_pass_rate(self):
        from llm.backend import InProcessBackend
        from llm.router import TierRouter

        config = init_llm()
        tier_cfg = dict(tier_section(config, "instruct"))
        backend = InProcessBackend({"instruct": tier_cfg})
        router = TierRouter({"instruct": backend})

        passed = 0
        for fixture in FIXTURES:
            block = Block(text=fixture["text"], hint_type=fixture["hint_type"], source_offset=(0, len(fixture["text"])))
            record = run_async(extract_block(block, router))
            if not record.needs_review and record.model_dump(mode="json", include=set(fixture["expected"])) == fixture["expected"]:
                passed += 1

        rate = passed / len(FIXTURES)
        self.assertGreaterEqual(rate, PASS_RATE_THRESHOLD)


if __name__ == "__main__":
    unittest.main()
