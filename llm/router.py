"""TierRouter: one ServerBackend shared by every tier, dispatched by model name.

`chat()` on the router is the only entry point the rest of the codebase
touches — llm/pipeline.py never imports ServerBackend directly.
"""
import logging

from llm.backend import ServerBackend
from llm.config import TIERS

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


class TierRouter:
    def __init__(self, backend: ServerBackend, models: dict[str, str]):
        self._backend = backend
        self._models = models

    async def chat(self, tier: str, messages: list[dict], **kw) -> str:
        model = self._models.get(tier)
        if not model:
            raise ConfigError(f"no model configured for tier: {tier}")
        return await self._backend.chat(model, messages, **kw)

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


def build_router(config) -> TierRouter:
    """Build the single ServerBackend + tier->model_name map from config.
    No health check here — a swap-router server can be "down" for a model
    that hasn't been loaded yet, that's what `doctor`'s real grammar-
    constrained call is for, not a bare reachability probe at startup."""
    server_cfg = config["server"]
    backend = ServerBackend(
        base_url=server_cfg["url"],
        grammar_mode=server_cfg.get("grammar_mode", "grammar_field"),
        timeout=server_cfg.getfloat("timeout", 30.0),
    )
    models = dict(config["models"])
    return TierRouter(backend, models)
