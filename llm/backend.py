"""LLM backend: a single external OpenAI-compatible server.

One `ServerBackend` instance serves every tier — the server (a llama-swap
style router) loads the right model on demand based on the request's
`"model"` field, so there's no per-tier backend resolution to do; `chat()`
just takes the model name to request.
"""
import asyncio
import logging

import aiohttp

from llm.grammar import to_gbnf

logger = logging.getLogger(__name__)

# Bounds concurrent outbound calls to the server, mirroring hipoclient.py's
# module-level _hipocrate_semaphore pattern.
_llm_semaphore = asyncio.Semaphore(6)


class ServerBackend:
    """aiohttp client for an OpenAI-compatible /v1/chat/completions server."""

    def __init__(self, base_url: str, grammar_mode: str = "grammar_field", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.grammar_mode = grammar_mode
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    def _client(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def close(self):
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def health(self) -> bool:
        try:
            async with _llm_semaphore:
                async with self._client().get(f"{self.base_url}/health", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    return resp.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False

    async def chat(self, model: str, messages: list[dict], *, json_schema: dict | None = None,
                    max_tokens: int = 512, temperature: float = 0.0) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_schema:
            grammar = to_gbnf(json_schema)
            if self.grammar_mode == "response_format":
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "extraction", "schema": json_schema},
                }
            else:
                payload["grammar"] = grammar

        async with _llm_semaphore:
            async with self._client().post(f"{self.base_url}/v1/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                data = await resp.json()
                content = data["choices"][0]["message"]["content"]
                return strip_think_block(content)


def strip_think_block(text: str) -> str:
    """Strip a <think>...</think> reasoning block, if present, before validation.

    The THINKING tier's actual delimiter should be confirmed against that
    model's chat template via `doctor`; this covers the common case.
    """
    start = text.find("<think>")
    end = text.find("</think>")
    if start != -1 and end != -1 and end > start:
        return (text[:start] + text[end + len("</think>"):]).strip()
    return text
