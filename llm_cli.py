#!/usr/bin/env python3
"""HippoBridge LLM subsystem entrypoint: extract / doctor / serve.

Standalone script, independent of hipobridge.py's own scraping-proxy
entrypoint — same "flat module, argparse, asyncio.run" shape, different
process.
"""
import argparse
import asyncio
import json
import logging
import sys

from aiohttp import web

from llm.config import TIERS, init_llm
from llm.pipeline import ExtractionResult, extract_document
from llm.router import build_router

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger("llm_cli")


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
    router = await build_router(config)
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
    """Tiny real grammar-constrained call: does this backend actually honor
    `json_schema`, or does it silently fall back to unconstrained text?

    Empirically, a server can echo the grammar back in its own
    generation_settings as "accepted" while still not applying it to
    sampling (confirmed against a real llama-server build on this
    machine — see llm/grammar.py's _gbnf_literal docstring for the related
    literal-escaping bug this uncovered). The only reliable check is
    driving one real call and inspecting the output shape.
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
    router = await build_router(config)
    try:
        status = await router.status()
        for tier in TIERS:
            info = status.get(tier, {})
            print(f"{tier}: backend={info.get('backend')} healthy={info.get('healthy')}")
            if info.get("healthy"):
                grammar_result = await _check_grammar_constrained(router, tier)
                print(f"  grammar-constrained call: {grammar_result}")
    finally:
        await router.close()
    return 0


async def cmd_serve(args) -> int:
    config = init_llm(args.config)
    router = await build_router(config)

    async def handle_extract(request: web.Request) -> web.Response:
        body = await request.json()
        text = body.get("text", "")
        result = await extract_document(text, router)
        return web.json_response(_result_to_json(result))

    async def on_cleanup(app):
        await router.close()

    app = web.Application()
    app.router.add_post("/extract", handle_extract)
    app.on_cleanup.append(on_cleanup)

    server_cfg = config["server"]
    host = args.host or server_cfg.get("host", "0.0.0.0")
    port = args.port or server_cfg.getint("port", 44661)

    logger.info(f"Starting LLM extraction server on {host}:{port} (internal use only — no auth)")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
    return 0


def main():
    parser = argparse.ArgumentParser(description="HippoBridge LLM structured-extraction subsystem")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="one-shot extraction against a file or stdin")
    extract_parser.add_argument("path", help="path to a document, or - for stdin")
    extract_parser.add_argument("--format", choices=["json", "markdown"], default="json")
    extract_parser.add_argument("--config", default="llm.cfg")

    doctor_parser = subparsers.add_parser("doctor", help="report resolved backend/health per tier")
    doctor_parser.add_argument("--config", default="llm.cfg")

    serve_parser = subparsers.add_parser("serve", help="run the long-lived extraction server")
    serve_parser.add_argument("--host", default=None)
    serve_parser.add_argument("--port", type=int, default=None)
    serve_parser.add_argument("--config", default="llm.cfg")

    args = parser.parse_args()
    handlers = {"extract": cmd_extract, "doctor": cmd_doctor, "serve": cmd_serve}

    try:
        exit_code = asyncio.run(handlers[args.command](args))
    except KeyboardInterrupt:
        exit_code = 130
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
