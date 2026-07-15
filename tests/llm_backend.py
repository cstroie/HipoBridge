import json
import unittest

from aiohttp import web

from llm.backend import ServerBackend
from tests.llm_async_helper import run_async


def _make_app(grammar_mode_seen: list):
    async def health(request):
        return web.json_response({"status": "ok"})

    async def chat_completions(request):
        body = await request.json()
        grammar_mode_seen.append("response_format" if "response_format" in body else "grammar_field")
        return web.json_response({"choices": [{"message": {"content": '{"ok": true}'}}]})

    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_post("/v1/chat/completions", chat_completions)
    return app


class TestServerBackend(unittest.TestCase):
    def test_health_and_chat_grammar_field_mode(self):
        async def scenario():
            seen = []
            app = _make_app(seen)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()
            port = site._server.sockets[0].getsockname()[1]
            try:
                backend = ServerBackend(f"http://127.0.0.1:{port}", grammar_mode="grammar_field")
                self.assertTrue(await backend.health())
                result = await backend.chat("instruct", [{"role": "user", "content": "hi"}],
                                             json_schema={"type": "object", "properties": {}})
                self.assertEqual(json.loads(result), {"ok": True})
                self.assertEqual(seen, ["grammar_field"])
                await backend.close()
            finally:
                await runner.cleanup()

        run_async(scenario())

    def test_chat_response_format_mode(self):
        async def scenario():
            seen = []
            app = _make_app(seen)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()
            port = site._server.sockets[0].getsockname()[1]
            try:
                backend = ServerBackend(f"http://127.0.0.1:{port}", grammar_mode="response_format")
                await backend.chat("instruct", [{"role": "user", "content": "hi"}],
                                    json_schema={"type": "object", "properties": {}})
                self.assertEqual(seen, ["response_format"])
                await backend.close()
            finally:
                await runner.cleanup()

        run_async(scenario())


if __name__ == "__main__":
    unittest.main()
