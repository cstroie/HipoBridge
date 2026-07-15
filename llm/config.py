"""Tier config for the LLM subsystem: backend choice, paths, URLs, context sizes.

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
        "default_extraction_tier": "instruct",
        "comparison_tier": "thinking",
        "narration_max_sentences": "5",
        "retry_on_validation_failure": "true",
    },
    "server": {
        "host": "0.0.0.0",
        "port": "44661",
    },
    "tier:nano": {
        "backend": "inprocess",
        "server_url": "",
        "server_model_name": "",
        "server_grammar_mode": "grammar_field",
        "local_path": "",
        "n_ctx": "4096",
        "n_threads": "4",
    },
    "tier:micro": {
        "backend": "inprocess",
        "server_url": "",
        "server_model_name": "",
        "server_grammar_mode": "grammar_field",
        "local_path": "",
        "n_ctx": "4096",
        "n_threads": "4",
    },
    "tier:instruct": {
        "backend": "auto",
        "server_url": "http://127.0.0.1:8080",
        "server_model_name": "",
        "server_grammar_mode": "grammar_field",
        "local_path": "",
        "n_ctx": "8192",
        "n_threads": "8",
    },
    "tier:thinking": {
        "backend": "inprocess",
        "server_url": "",
        "server_model_name": "",
        "server_grammar_mode": "grammar_field",
        "local_path": "",
        "n_ctx": "8192",
        "n_threads": "8",
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


def tier_section(config: configparser.ConfigParser, tier: str) -> configparser.SectionProxy:
    section = f"tier:{tier}"
    if section not in config:
        raise ValueError(f"unknown tier: {tier}")
    return config[section]
