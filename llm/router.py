"""LLMClient: one ServerBackend for the active provider, dispatched by tier.

`chat()`/`chat_stream()` are the only entry points the rest of the codebase
touches — callers never import ServerBackend directly.
"""
import logging
from typing import AsyncIterator

from llm.backend import ServerBackend
from llm.config import TIERS, select_provider

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


class LLMClient:
    def __init__(self, backend: ServerBackend, models: dict[str, str], language: str = "English"):
        self._backend = backend
        self._models = models
        self.language = language

    async def chat(self, tier: str, messages: list[dict], **kw) -> str:
        model = self._models.get(tier)
        if not model:
            raise ConfigError(f"no model configured for tier: {tier}")
        return await self._backend.chat(model, messages, **kw)

    async def chat_stream(self, tier: str, messages: list[dict], **kw) -> AsyncIterator[str]:
        model = self._models.get(tier)
        if not model:
            raise ConfigError(f"no model configured for tier: {tier}")
        async for piece in self._backend.chat_stream(model, messages, **kw):
            yield piece

    def model_for(self, tier: str) -> str | None:
        return self._models.get(tier)

    @property
    def base_url(self) -> str:
        return self._backend.base_url

    async def health(self) -> bool:
        return await self._backend.health()

    async def status(self) -> dict:
        healthy = await self._backend.health()
        return {tier: {"model": self._models.get(tier), "healthy": healthy} for tier in TIERS}

    async def close(self):
        await self._backend.close()


def build_client(config) -> LLMClient:
    """Build the ServerBackend + tier->model map for the active provider.
    No startup health check — a swap-router server can be "down" for a model
    that hasn't been loaded yet."""
    url, key, models = select_provider(config)
    llm_section = config["llm"] if config.has_section("llm") else {}
    timeout = llm_section.getfloat("timeout", 60.0) if config.has_section("llm") else 60.0
    language = (llm_section.get("language", "English") or "English").strip()
    backend = ServerBackend(base_url=url, key=key, timeout=timeout)
    return LLMClient(backend, models, language=language)
