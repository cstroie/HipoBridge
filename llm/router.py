"""LLMClient: one ServerBackend for the active provider, dispatched by tier.

`chat()`/`chat_stream()` are the only entry points the rest of the codebase
touches — callers never import ServerBackend directly.
"""
import logging
from typing import AsyncIterator

from llm.backend import ServerBackend
from llm.config import TIERS, select_provider

logger = logging.getLogger(__name__)


DEFAULT_CONTEXT = 8192


class ConfigError(Exception):
    pass


class LLMClient:
    def __init__(self, backend: ServerBackend, models: dict[str, str], language: str = "English",
                 temperature: float = 0.1, anonymize: bool = True,
                 context: int | None = None):
        self._backend = backend
        self._models = models
        self.language = language
        self.temperature = temperature
        self.anonymize = anonymize
        # None = auto: DEFAULT_CONTEXT until resolve_context() probes the server.
        self.context_auto = context is None
        self.context = context or DEFAULT_CONTEXT

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

    async def list_models(self) -> list[str]:
        return await self._backend.list_models()

    def configured_models(self) -> dict[str, str]:
        return dict(self._models)

    async def resolve_context(self, tiers=("default", "medical")) -> None:
        """For `context = auto`: ask the server for the context of the models
        the prompts actually use and keep the smallest (the budget has to fit
        every tier). Falls back to DEFAULT_CONTEXT, with a log line, when the
        server reports nothing usable. No-op for an explicit integer."""
        if not self.context_auto:
            return
        probed = await self._backend.probe_context()
        models = {self._models[t] for t in tiers if self._models.get(t)}
        sizes = {m: probed.get(m, probed.get("*")) for m in models}
        known = [n for n in sizes.values() if n]
        if known:
            self.context = min(known)
            logger.info(f"LLM context (auto): {self.context} tokens, from {sizes}")
        else:
            logger.warning(f"LLM context (auto): server reports none for {sorted(models)}; "
                           f"using {DEFAULT_CONTEXT} (set `context` explicitly to override)")

    async def status(self) -> dict:
        healthy = await self._backend.health()
        return {tier: {"model": self._models.get(tier), "healthy": healthy} for tier in TIERS}

    async def close(self):
        await self._backend.close()


def _parse_context(value: str) -> int | None:
    """`auto` (or empty) -> None; otherwise a positive token count."""
    value = (value or "auto").strip().lower()
    if value == "auto":
        return None
    try:
        n = int(value)
    except ValueError:
        n = 0
    if n <= 0:
        raise ConfigError(f"[provider] context must be 'auto' or a positive integer, got {value!r}")
    return n


def build_client(config) -> LLMClient:
    """Build the ServerBackend + tier->model map for the active provider.
    No startup health check — a swap-router server can be "down" for a model
    that hasn't been loaded yet."""
    url, key, models = select_provider(config)
    llm_section = config["llm"] if config.has_section("llm") else {}
    timeout = llm_section.getfloat("timeout", 60.0) if config.has_section("llm") else 60.0
    language = (llm_section.get("language", "English") or "English").strip()
    temperature = llm_section.getfloat("temperature", 0.1) if config.has_section("llm") else 0.1
    backend = ServerBackend(base_url=url, key=key, timeout=timeout)
    section = config[f"provider:{llm_section.get('provider', 'default')}"]
    anonymize = section.getboolean("anonymize", True)
    return LLMClient(backend, models, language=language, temperature=temperature, anonymize=anonymize,
                     context=_parse_context(section.get("context", "auto")))
