"""Config for the LLM subsystem: one external OpenAI-compatible server, one
model name per tier.

Mirrors hipobridge.py's load_config() layering exactly: defaults -> llm.cfg
-> local.cfg (later wins). Deliberately a separate file/section namespace
from hipobridge.cfg's own [server] so the two don't collide.
"""
import configparser
import logging
import os

logger = logging.getLogger(__name__)

TIERS = ("nano", "micro", "instruct", "thinking")

LLM_DEFAULTS = {
    "pipeline": {
        "comparison_tier": "thinking",
        "narration_max_sentences": "5",
    },
    "server": {
        # The existing OpenAI-compatible llama-server (a swap-router: loads
        # the model named in each request's "model" field on demand).
        "url": "http://127.0.0.1:8080",
        "grammar_mode": "grammar_field",
        "timeout": "30",
    },
    "models": {
        # Model names as registered on that server — must match its own
        # aliases/presets exactly (check with `llm_cli.py doctor` or
        # GET /v1/models on the server) — these are illustrative defaults.
        "nano": "LFM2.5-230M",
        "micro": "LFM2.5-350M",
        "instruct": "LFM2.5-1.2b-Instruct",
        "thinking": "LFM2.5-1.2b-Thinking",
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
