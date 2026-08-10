"""Project logger factory aligned with БЗ module shape.

Django ``LOGGING`` in ``config.settings`` owns handlers/formatters.
Modules call ``logger = setup_logger("hoocon.leads")`` instead of bare
``logging.getLogger`` so the entrypoint matches БЗ ``_setup_logger``.
"""

from __future__ import annotations

import logging


def setup_logger(name: str) -> logging.Logger:
    """Return a named logger (handlers come from Django LOGGING).

    Args:
        name: logger name (prefer ``hoocon.<app>`` or ``__name__``).

    Returns:
        Logger instance for the given name.
    """
    return logging.getLogger(name)
