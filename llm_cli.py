#!/usr/bin/env python3
"""HippoBridge LLM subsystem CLI: extract / doctor.

One-shot calls against the external OpenAI-compatible server configured in
llm.cfg — no process to keep alive. hipobridge.py's AI tab talks to that
same server directly and in-process; this script exists purely for
testing/debugging the pipeline without going through the web UI.
"""
import argparse
import asyncio
import json
import sys

from llm.config import TIERS, init_llm
from llm.pipeline import ExtractionResult, extract_document
from llm.router import build_router


def _result_to_json(result: ExtractionResult) -> dict:
    return {
        "records": [r.model_dump(mode="json") for r in result.records],
        "timeline": [
            {
                "date": e.date.isoformat() if e.date else None,
                "ordered": e.ordered,
                "delta_note": e.delta_note,
                "record": e.record.model_dump(mode="json"),
            }
            for e in result.timeline
        ],
    }


async def cmd_extract(args) -> int:
    config = init_llm(args.config)
    router = build_router(config)
    try:
        document = sys.stdin.read() if args.path == "-" else open(args.path, encoding="utf-8").read()
        result = await extract_document(document, router)
    finally:
        await router.close()

    if args.format == "markdown":
        for record in result.records:
            flag = " [NEEDS REVIEW]" if getattr(record, "needs_review", False) else ""
            print(f"- {record.type}{flag}: {record.model_dump(exclude={'needs_review', 'raw_source'})}")
    else:
        print(json.dumps(_result_to_json(result), indent=2))

    return 1 if any(getattr(r, "needs_review", False) for r in result.records) else 0


async def _check_grammar_constrained(router, tier: str) -> str:
    """Tiny real grammar-constrained call: does this server actually honor
    `json_schema` for this tier's model, or does it silently fall back to
    unconstrained text?

    Empirically, a server can echo the grammar back in its own
    generation_settings as "accepted" while still not applying it to
    sampling (confirmed against a real llama-server build — see
    llm/grammar.py's _gbnf_literal docstring for the related literal-
    escaping bug this uncovered). The only reliable check is driving one
    real call and inspecting the output shape.
    """
    from llm.schemas import ClinicalNoteRecord, model_extraction_schema

    schema = model_extraction_schema(ClinicalNoteRecord)
    messages = [
        {"role": "system", "content": "Return only a JSON object matching the given shape."},
        {"role": "user", "content": "Patient seen for routine follow-up, no new complaints."},
    ]
    try:
        raw = await router.chat(tier, messages, json_schema=schema, max_tokens=80, temperature=0.1)
    except Exception as exc:
        return f"FAIL (call raised: {exc})"

    stripped = raw.strip()
    if not stripped.startswith("{"):
        return f"FAIL (grammar not enforced — output didn't start with '{{': {stripped[:60]!r})"
    try:
        ClinicalNoteRecord.model_validate_json(stripped)
    except Exception as exc:
        return f"FAIL (grammar-shaped but invalid: {exc})"
    return "OK"


async def cmd_doctor(args) -> int:
    config = init_llm(args.config)
    router = build_router(config)
    try:
        server_healthy = await router.health()
        print(f"server: url={router.base_url} healthy={server_healthy}")
        for tier in TIERS:
            model = router.model_for(tier)
            print(f"{tier}: model={model}")
            if model:
                grammar_result = await _check_grammar_constrained(router, tier)
                print(f"  grammar-constrained call: {grammar_result}")
    finally:
        await router.close()
    return 0


def main():
    parser = argparse.ArgumentParser(description="HippoBridge LLM structured-extraction subsystem")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="one-shot extraction against a file or stdin")
    extract_parser.add_argument("path", help="path to a document, or - for stdin")
    extract_parser.add_argument("--format", choices=["json", "markdown"], default="json")
    extract_parser.add_argument("--config", default="llm.cfg")

    doctor_parser = subparsers.add_parser("doctor", help="check the server + each tier's model/grammar")
    doctor_parser.add_argument("--config", default="llm.cfg")

    args = parser.parse_args()
    handlers = {"extract": cmd_extract, "doctor": cmd_doctor}

    try:
        exit_code = asyncio.run(handlers[args.command](args))
    except KeyboardInterrupt:
        exit_code = 130
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
