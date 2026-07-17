"""Config for the LLM subsystem: one or more OpenAI-compatible providers, one
active at a time, each exposing three model tiers.

Mirrors hipobridge.py's load_config() layering exactly: defaults -> llm.cfg
-> local.cfg (later wins). Deliberately a separate file/section namespace
from hipobridge.cfg's own [server] so the two don't collide.

configparser has no nesting, so each provider is a prefixed section
`[provider:<name>]` with `url`, `key` (empty = no auth) and one model name
per tier. `[llm] provider = <name>` selects the active one; local.cfg
overrides that key to switch providers without touching llm.cfg.

Every call ships raw PHI (names, DOB, CNP) to the provider url — provider
config must stay local/trusted. The `key` field enables remote providers;
that is the operator's responsibility, not enforced here.
"""
import configparser
import logging
import os

logger = logging.getLogger(__name__)

TIERS = ("lite", "default", "medical")

_PROVIDER_PREFIX = "provider:"

LLM_DEFAULTS = {
    "llm": {
        "provider": "default",
        "timeout": "60",
    },
    "provider:default": {
        # Local OpenAI-compatible server (llama-server, LM Studio, ...).
        # The url is the full OpenAI base and includes the /v1 suffix.
        "url": "http://127.0.0.1:8080/v1",
        "key": "",
        # Model names as registered on that server — must match its own
        # aliases/presets exactly (check GET /v1/models on the server).
        "lite": "LFM2.5-230M",
        "default": "LFM2-2.6B-Transcript",
        "medical": "medgemma-4b-it",
    },
}


def init_llm(config_path: str = "llm.cfg", local_path: str = "local.cfg") -> configparser.ConfigParser:
    """Load llm.cfg then overlay local.cfg if present. Called at startup, not import time."""
    config = configparser.ConfigParser()
    config.read_dict(LLM_DEFAULTS)

    if os.path.exists(config_path):
        logger.info(f"Loading {config_path} configuration")
        config.read(config_path)
    else:
        logger.info(f"{config_path} not found, using default configuration")

    if os.path.exists(local_path):
        logger.info(f"Loading {local_path} configuration (overrides {config_path})")
        config.read(local_path)

    return config


def select_provider(config: configparser.ConfigParser) -> tuple[str, str, dict]:
    """Resolve the active provider into (url, key, {tier: model_name}).

    The active provider is `[llm] provider`; its section is
    `[provider:<name>]`. Raises KeyError with a clear message if the named
    provider section is missing (misconfiguration should fail loudly at
    startup, not silently fall back)."""
    llm_section = config["llm"] if config.has_section("llm") else {}
    name = llm_section.get("provider", "default")
    section_name = f"{_PROVIDER_PREFIX}{name}"
    if not config.has_section(section_name):
        available = [s[len(_PROVIDER_PREFIX):] for s in config.sections()
                     if s.startswith(_PROVIDER_PREFIX)]
        raise KeyError(
            f"LLM provider '{name}' not configured (looked for [{section_name}]); "
            f"available providers: {available or 'none'}")
    section = config[section_name]
    url = section.get("url", "").rstrip("/")
    key = section.get("key", "").strip()
    models = {tier: section.get(tier, "").strip() for tier in TIERS}
    return url, key, models
