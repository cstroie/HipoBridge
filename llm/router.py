"""TierRouter: resolves and holds one backend per tier at startup.

`chat()` on the router is the only entry point the rest of the codebase
touches — llm/pipeline.py never imports ServerBackend/InProcessBackend
directly.
"""
import logging

from llm.backend import InProcessBackend, ServerBackend
from llm.config import TIERS, tier_section

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


class TierRouter:
    def __init__(self, routes: dict):
        self._routes = routes

    async def chat(self, tier: str, messages: list[dict], **kw) -> str:
        if tier not in self._routes:
            raise ConfigError(f"no backend resolved for tier: {tier}")
        return await self._routes[tier].chat(tier, messages, **kw)

    def backend_name(self, tier: str) -> str:
        backend = self._routes.get(tier)
        return type(backend).__name__ if backend is not None else "unknown"

    async def status(self) -> dict:
        result = {}
        for tier, backend in self._routes.items():
            result[tier] = {
                "backend": type(backend).__name__,
                "healthy": await backend.health(),
            }
        return result

    async def close(self):
        for backend in self._routes.values():
            close = getattr(backend, "close", None)
            if close is not None:
                await close()


def _server_backend_for(tier_cfg) -> ServerBackend:
    return ServerBackend(
        base_url=tier_cfg["server_url"],
        model_name=tier_cfg.get("server_model_name") or None,
        grammar_mode=tier_cfg.get("server_grammar_mode", "grammar_field"),
    )


async def build_router(config) -> TierRouter:
    """Resolve one backend per configured tier.

    A single llama-server process normally serves one model, so `auto`
    only makes sense for a tier whose server is known to cover it —
    whenever a server multiplexes fewer than all tiers, pin tiers
    explicitly (backend = server / inprocess) in llm.cfg/local.cfg rather
    than relying on `auto` to guess which model is loaded.
    """
    routes = {}
    inprocess_tier_paths = {}

    # First pass: collect inprocess-bound tiers so one InProcessBackend
    # instance can hold every locally-loaded model (matches the spec's
    # "one Llama instance + lock per tier" design without instantiating
    # a separate InProcessBackend object per tier).
    for tier in TIERS:
        tier_cfg = tier_section(config, tier)
        backend_choice = tier_cfg.get("backend", "auto")
        if backend_choice == "inprocess":
            inprocess_tier_paths[tier] = dict(tier_cfg)

    shared_inprocess = InProcessBackend(inprocess_tier_paths) if inprocess_tier_paths else None

    for tier in TIERS:
        tier_cfg = tier_section(config, tier)
        backend_choice = tier_cfg.get("backend", "auto")

        if backend_choice == "server":
            routes[tier] = _server_backend_for(tier_cfg)
        elif backend_choice == "inprocess":
            routes[tier] = shared_inprocess
        elif backend_choice == "auto":
            candidate = _server_backend_for(tier_cfg)
            if tier_cfg.get("server_url") and await candidate.health():
                routes[tier] = candidate
            else:
                await candidate.close()
                if tier not in inprocess_tier_paths:
                    inprocess_tier_paths[tier] = dict(tier_cfg)
                    if shared_inprocess is not None:
                        shared_inprocess.add_tier(tier, dict(tier_cfg))
                    else:
                        shared_inprocess = InProcessBackend(inprocess_tier_paths)
                routes[tier] = shared_inprocess
        else:
            raise ConfigError(f"unknown backend for tier {tier}: {backend_choice}")

    return TierRouter(routes)
