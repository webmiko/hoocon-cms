"""Tests for config.logging_utils (audit P3-12)."""

from __future__ import annotations

from config.logging_utils import setup_logger


def test_setup_logger_returns_named_logger() -> None:
    """setup_logger returns logging.Logger with the requested name."""
    logger = setup_logger("hoocon.test.logging")
    assert logger.name == "hoocon.test.logging"
    assert setup_logger("hoocon.test.logging") is logger
