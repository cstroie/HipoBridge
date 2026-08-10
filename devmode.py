"""Process-wide dev/production mode flag.

Set once at startup (see hippobridge.py's --dev flag / HB_DEV env var) and
read by modules that want cheap-in-dev-only behavior — e.g. llm/prompts.py's
per-request mtime check for prompt template hot-reload, which should not pay
a stat() syscall per LLM call in production once prompts are stable.
"""

_dev_mode = False


def set_dev_mode(value: bool) -> None:
    global _dev_mode
    _dev_mode = bool(value)


def is_dev_mode() -> bool:
    return _dev_mode
