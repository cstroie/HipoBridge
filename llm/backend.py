"""LLM backend: a single external OpenAI-compatible provider.

One `ServerBackend` instance serves every tier — `chat()` just takes the
model name to request. Free-text completions only; no grammar/JSON-schema
constraint (the extraction pipeline that needed those is gone).
"""
import asyncio
import json
import logging
import time
from typing import AsyncIterator

import aiohttp

logger = logging.getLogger(__name__)

# Bounds concurrent outbound calls to the server, mirroring hippoclient.py's
# module-level _hipocrate_semaphore pattern.
_llm_semaphore = asyncio.Semaphore(6)


def _log_usage(model: str, elapsed: float, usage: dict) -> None:
    """Log which model actually served a call plus timing/throughput derived
    from the response's `usage` block and our own wall-clock measurement —
    LM Studio's `stats` field is present in the schema but empty in practice
    on this server, so tokens/sec has to be computed client-side rather than
    trusted from the response."""
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
    tps = completion_tokens / elapsed if elapsed > 0 else 0
    reasoning_note = f", {reasoning_tokens} reasoning" if reasoning_tokens else ""
    logger.info(
        f"LLM call: model={model} time={elapsed:.2f}s "
        f"prompt_tokens={prompt_tokens} completion_tokens={completion_tokens}{reasoning_note} "
        f"tps={tps:.1f}"
    )


class ServerBackend:
    """aiohttp client for an OpenAI-compatible /chat/completions server.

    `base_url` is the full OpenAI base (already includes /v1). `key`, when
    set, is sent as an `Authorization: Bearer` header — empty means no auth.
    """

    def __init__(self, base_url: str, key: str = "", timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self._key = key
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._key}"} if self._key else {}

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
                async with self._client().get(
                    f"{self.base_url}/models", headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    return resp.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False

    async def chat(self, model: str, messages: list[dict], *,
                    max_tokens: int = 512, temperature: float = 0.1) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "reasoning": {"effort": "none"},
        }
        start = time.monotonic()
        async with _llm_semaphore:
            async with self._client().post(
                f"{self.base_url}/chat/completions",
                json=payload, headers=self._headers()) as resp:
                resp.raise_for_status()
                data = await resp.json()
        elapsed = time.monotonic() - start
        _log_usage(data.get("model", model), elapsed, data.get("usage") or {})
        content = data["choices"][0]["message"]["content"]
        return strip_think_block(content)

    async def chat_stream(self, model: str, messages: list[dict], *,
                           max_tokens: int = 512,
                           temperature: float = 0.1) -> AsyncIterator[str]:
        """Stream a completion, yielding text pieces as they arrive.

        Only forwards `delta.content` — never `delta.reasoning_content`,
        which some models (gpt-oss/qwen-reasoning style) use for a separate
        chain-of-thought channel. A model that leaks its reasoning this way
        simply produces no visible stream instead of streaming garbage to
        the caller; callers still see it fail via an empty/short result.
        `strip_think_block()` is not applied per-chunk — callers should run
        it once over the fully accumulated text (inline `<think>` tags, if
        any slipped into `content` itself, would already have been yielded
        raw chunk-by-chunk before that point)."""
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "reasoning": {"effort": "none"},
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        start = time.monotonic()
        served_model = model
        usage = {}
        async with _llm_semaphore:
            async with self._client().post(
                f"{self.base_url}/chat/completions",
                json=payload, headers=self._headers()) as resp:
                resp.raise_for_status()
                async for raw in resp.content:
                    line = raw.decode("utf-8", "ignore").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    served_model = chunk.get("model", served_model)
                    # The final chunk (stream_options.include_usage) carries
                    # usage with an empty choices list — no delta to yield.
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    if chunk.get("error"):
                        # e.g. LM Studio's "event: error" line (context-length
                        # overflow and similar) — has no "choices" key, so
                        # without this check it would silently fall through
                        # the `if not choices: continue` below and vanish.
                        err = chunk["error"]
                        message = err.get("message") if isinstance(err, dict) else str(err)
                        raise RuntimeError(message or "LLM server returned an error")
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    piece = (choices[0].get("delta") or {}).get("content")
                    if piece:
                        yield piece
        _log_usage(served_model, time.monotonic() - start, usage)


def strip_think_block(text: str) -> str:
    """Strip a <think>...</think> reasoning block, if present — transcript
    and medical models may emit one before their answer."""
    start = text.find("<think>")
    end = text.find("</think>")
    if start != -1 and end != -1 and end > start:
        return (text[:start] + text[end + len("</think>"):]).strip()
    return text
