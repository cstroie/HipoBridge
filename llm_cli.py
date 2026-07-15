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

from llm.config import TIERS, init_llm, tier_section
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


async def cmd_doctor(args) -> int:
    config = init_llm(args.config)
    router = await build_router(config)
    try:
        status = await router.status()
        for tier in TIERS:
            info = status.get(tier, {})
            print(f"{tier}: backend={info.get('backend')} healthy={info.get('healthy')}")

        tier_cfg = tier_section(config, "instruct")
        if tier_cfg.get("backend") in ("server", "auto") and status.get("instruct", {}).get("healthy"):
            print(f"instruct: server_grammar_mode configured as "
                  f"'{tier_cfg.get('server_grammar_mode')}' (verify against a real grammar-constrained "
                  f"call once the actual target model is loaded on that server)")
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
