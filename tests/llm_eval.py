"""Fixture-based extraction pass-rate harness.

Self-skips unless the configured external LLM server is actually
reachable — this is the one test group meant to run against a real model,
not a stub backend. Not wired into "all" by default for that reason; run
explicitly via `python3 runtests.py llm` once the server is up.
"""
import unittest

from llm.config import init_llm
from llm.pipeline import extract_block
from llm.router import build_router
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


def _server_reachable() -> bool:
    router = build_router(init_llm())
    try:
        return run_async(router.health())
    finally:
        run_async(router.close())


@unittest.skipUnless(_server_reachable(), "configured LLM server (llm.cfg) is not reachable")
class TestFixtureEvalHarness(unittest.TestCase):
    def test_pass_rate(self):
        router = build_router(init_llm())

        passed = 0
        for fixture in FIXTURES:
            block = Block(text=fixture["text"], hint_type=fixture["hint_type"], source_offset=(0, len(fixture["text"])))
            record = run_async(extract_block(block, router))
            if not record.needs_review and record.model_dump(mode="json", include=set(fixture["expected"])) == fixture["expected"]:
                passed += 1

        run_async(router.close())
        rate = passed / len(FIXTURES)
        self.assertGreaterEqual(rate, PASS_RATE_THRESHOLD)


if __name__ == "__main__":
    unittest.main()
