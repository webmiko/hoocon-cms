"""Canonical working-medium copy for all Hoocon ball valves / LAV.

Default medium is cold/hot water. Ethylene glycol solution is available
only on special order (≤ 50 %). Keep brass BV*, H81 kits, and H8205 LAV
in sync via these constants.
"""

from __future__ import annotations

# Compact ТТХ / highlight value (cards, specs tab, compare).
WORKING_MEDIUM_ATTR = "холодная и горячая вода (раствор этиленгликоля ≤ 50 % — по спецзаказу)"

# Product description bullet (multi-line, after «Назначение и особенности:»).
WORKING_MEDIUM_BULLET = (
    "– Рабочая среда (по умолчанию): холодная и горячая вода;\n"
    "  по специальному заказу — раствор этиленгликоля "
    "концентрацией не более 50 %."
)

# One-line prose inside SKU lead paragraphs.
WORKING_MEDIUM_INLINE = "Рабочая среда — холодная и горячая вода (раствор этиленгликоля ≤ 50 % — по спецзаказу)"
