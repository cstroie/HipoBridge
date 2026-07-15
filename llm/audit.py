"""Privacy-safe audit logging for the LLM subsystem.

Source documents contain real names, DOB, and national ID numbers. Log
metadata only, never content. If a debug mode is ever added for
development, it must be gated behind an explicit config flag and
documented as never-safe against real patient data.
"""
import hashlib
import logging

logger = logging.getLogger("llm.audit")


def log_extraction(block_text: str, tier_used: str, backend_used: str,
                    validation_result: str, latency_ms: float) -> None:
    """validation_result: 'ok' | 'retried' | 'needs_review'"""
    block_hash = hashlib.sha256(block_text.encode("utf-8")).hexdigest()[:16]
    logger.info(
        "extraction block_hash=%s tier=%s backend=%s result=%s latency_ms=%.1f",
        block_hash, tier_used, backend_used, validation_result, latency_ms,
    )
