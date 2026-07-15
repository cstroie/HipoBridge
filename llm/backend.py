"""LLM backend abstraction.

Both `ServerBackend` (talks to an existing llama.cpp server) and
`InProcessBackend` (self-hosted llama-cpp-python) implement the same
Protocol, so `llm/pipeline.py` never branches on which one it's talking to
— that decision is made once, per tier, in `llm/router.py`.
"""
import asyncio
import logging
from typing import Protocol

import aiohttp

from llm.grammar import to_gbnf

logger = logging.getLogger(__name__)

# Bounds concurrent outbound calls to an external llama.cpp server, mirroring
# hipoclient.py's module-level _hipocrate_semaphore pattern.
_llm_semaphore = asyncio.Semaphore(6)


class LLMBackend(Protocol):
    async def chat(
        self,
        tier: str,
        messages: list[dict],
        *,
        json_schema: dict | None = None,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> str: ...

    async def health(self) -> bool: ...


class ServerBackend:
    """HTTP client for an existing llama.cpp server (aiohttp, not httpx)."""

    def __init__(self, base_url: str, model_name: str | None = None,
                 grammar_mode: str = "grammar_field", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name or "default"
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

    async def chat(self, tier, messages, *, json_schema=None, max_tokens=512, temperature=0.0) -> str:
        payload = {
            "model": self.model_name,
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
                return data["choices"][0]["message"]["content"]


class InProcessBackend:
    """Self-hosted GGUF inference via llama-cpp-python, one model per tier."""

    def __init__(self, tier_paths: dict[str, dict]):
        # tier_paths: {tier: {"local_path": ..., "n_ctx": ..., "n_threads": ...}}
        self._tier_paths = tier_paths
        self._models: dict[str, object] = {}
        self._locks: dict[str, asyncio.Lock] = {tier: asyncio.Lock() for tier in tier_paths}
        self._think_delimiters: dict[str, tuple[str, str]] = {}

    def add_tier(self, tier: str, tier_cfg: dict) -> None:
        """Register a tier discovered after construction (e.g. an `auto`
        tier that fell back to inprocess once its server health check failed)."""
        self._tier_paths[tier] = tier_cfg
        self._locks.setdefault(tier, asyncio.Lock())

    async def load(self, tier: str) -> None:
        if tier in self._models:
            return
        from llama_cpp import Llama  # imported lazily — optional dependency

        cfg = self._tier_paths[tier]
        loop = asyncio.get_event_loop()
        model = await loop.run_in_executor(
            None,
            lambda: Llama(
                model_path=cfg["local_path"],
                n_ctx=int(cfg.get("n_ctx", 4096)),
                n_threads=int(cfg.get("n_threads", 4)),
            ),
        )
        self._models[tier] = model

    async def health(self) -> bool:
        return bool(self._models)

    async def chat(self, tier, messages, *, json_schema=None, max_tokens=512, temperature=0.0) -> str:
        from llama_cpp import LlamaGrammar

        await self.load(tier)
        grammar = LlamaGrammar.from_string(to_gbnf(json_schema)) if json_schema else None
        loop = asyncio.get_event_loop()
        async with self._locks[tier]:
            result = await loop.run_in_executor(
                None,
                lambda: self._models[tier].create_chat_completion(
                    messages=messages, grammar=grammar, max_tokens=max_tokens, temperature=temperature,
                ),
            )
        content = result["choices"][0]["message"]["content"]
        return strip_think_block(content)


def strip_think_block(text: str) -> str:
    """Strip a <think>...</think> reasoning block, if present, before validation.

    The THINKING tier's actual delimiter should be confirmed against that
    GGUF's chat_template at doctor-time; this covers the common case.
    """
    start = text.find("<think>")
    end = text.find("</think>")
    if start != -1 and end != -1 and end > start:
        return (text[:start] + text[end + len("</think>"):]).strip()
    return text
