"""LLM backend: a single external OpenAI-compatible provider.

One `ServerBackend` instance serves every tier — `chat()` just takes the
model name to request. Free-text completions only; no grammar/JSON-schema
constraint (the extraction pipeline that needed those is gone).
"""
import asyncio
import logging

import aiohttp

logger = logging.getLogger(__name__)

# Bounds concurrent outbound calls to the server, mirroring hipoclient.py's
# module-level _hipocrate_semaphore pattern.
_llm_semaphore = asyncio.Semaphore(6)


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
        }
        async with _llm_semaphore:
            async with self._client().post(
                f"{self.base_url}/chat/completions",
                json=payload, headers=self._headers()) as resp:
                resp.raise_for_status()
                data = await resp.json()
                content = data["choices"][0]["message"]["content"]
                return strip_think_block(content)


def strip_think_block(text: str) -> str:
    """Strip a <think>...</think> reasoning block, if present — transcript
    and medical models may emit one before their answer."""
    start = text.find("<think>")
    end = text.find("</think>")
    if start != -1 and end != -1 and end > start:
        return (text[:start] + text[end + len("</think>"):]).strip()
    return text
