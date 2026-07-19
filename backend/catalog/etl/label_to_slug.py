"""Map Russian ТТХ labels (and legacy Attribute names) to canonical slugs."""

from __future__ import annotations

import re

from catalog.etl.attr_groups import (
    ATTR_GROUP_ELECTRICAL,
    ATTR_GROUP_FUNCTIONAL,
    ATTR_GROUP_HYDRAULIC,
    ATTR_GROUP_MATERIALS,
    ATTR_GROUP_OPERATING,
    ATTR_GROUP_SIZE,
    ATTR_GROUP_VALVE,
)

# Canonical attribute definitions: slug → (display name, unit, group).
CANONICAL_ATTRS: dict[str, tuple[str, str, str]] = {
    "voltage": ("Номинальное напряжение", "", ATTR_GROUP_ELECTRICAL),
    "voltage-range": ("Диапазон напряжения", "", ATTR_GROUP_ELECTRICAL),
    "power-consumption": ("Потребляемая мощность", "", ATTR_GROUP_ELECTRICAL),
    "transformer-va": ("Мощность трансформатора", "В·А", ATTR_GROUP_ELECTRICAL),
    "wire-cross-section": ("Сечение провода", "мм²", ATTR_GROUP_ELECTRICAL),
    "control-signal": ("Управляющий сигнал Y", "", ATTR_GROUP_ELECTRICAL),
    "feedback-signal": ("Обратная связь U", "", ATTR_GROUP_ELECTRICAL),
    "moment": ("Крутящий момент", "Нм", ATTR_GROUP_FUNCTIONAL),
    "damper-area": ("Площадь заслонки", "м²", ATTR_GROUP_FUNCTIONAL),
    "terminal-size": ("Сечение клемм", "мм²", ATTR_GROUP_FUNCTIONAL),
    "rotation-direction": ("Направление вращения", "", ATTR_GROUP_FUNCTIONAL),
    "manual-override": ("Ручное управление", "", ATTR_GROUP_FUNCTIONAL),
    "rotation-angle": ("Угол поворота", "°", ATTR_GROUP_FUNCTIONAL),
    "noise": ("Уровень шума", "дБ(A)", ATTR_GROUP_FUNCTIONAL),
    "position-indication": ("Индикация положения", "", ATTR_GROUP_FUNCTIONAL),
    "control": ("Управление", "", ATTR_GROUP_FUNCTIONAL),
    "aux-switch": ("Вспомогательный переключатель", "", ATTR_GROUP_FUNCTIONAL),
    "running-time": ("Время поворота", "с", ATTR_GROUP_FUNCTIONAL),
    "temp-sensor": ("Датчик температуры", "", ATTR_GROUP_FUNCTIONAL),
    "protection-class": ("Класс защиты", "", ATTR_GROUP_OPERATING),
    "ip-rating": ("Степень защиты корпуса", "", ATTR_GROUP_OPERATING),
    "ambient-temp": ("Температура окружающей среды", "°C", ATTR_GROUP_OPERATING),
    "storage-temp": ("Температура хранения", "°C", ATTR_GROUP_OPERATING),
    "humidity": ("Относительная влажность", "", ATTR_GROUP_OPERATING),
    "dimensions": ("Габаритные размеры", "мм", ATTR_GROUP_SIZE),
    "shaft-length": ("Длина вала заслонки", "мм", ATTR_GROUP_SIZE),
    "shaft-diameter": ("Диаметр вала", "мм", ATTR_GROUP_SIZE),
    "weight": ("Масса", "кг", ATTR_GROUP_SIZE),
    "dn": ("DN", "", ATTR_GROUP_VALVE),
    "ways": ("Вид крана", "", ATTR_GROUP_VALVE),
    "thread": ("Резьба", "", ATTR_GROUP_VALVE),
    "kvs": ("Kvs", "м³/ч", ATTR_GROUP_HYDRAULIC),
    "diff-pressure": ("Максимальный рабочий перепад давления", "МПа", ATTR_GROUP_HYDRAULIC),
    "compatible-actuators": ("Совместимый привод", "", ATTR_GROUP_VALVE),
    "bracket": ("Кронштейн", "", ATTR_GROUP_VALVE),
    "medium": ("Рабочая среда", "", ATTR_GROUP_OPERATING),
    "media-temp": ("Рабочая температура среды", "°C", ATTR_GROUP_OPERATING),
    "material": ("Материал корпуса", "", ATTR_GROUP_MATERIALS),
    "ball-stem-material": ("Золотниковый шток и шар", "", ATTR_GROUP_MATERIALS),
    "stem-seal": ("Двойное уплотнение штока", "", ATTR_GROUP_MATERIALS),
    "seat-seal": ("Уплотнение корпуса крана", "", ATTR_GROUP_MATERIALS),
    "flow-disk": ("Выпрямительный диск", "", ATTR_GROUP_MATERIALS),
    "height-actuator": ("Высота до верхнего края привода", "мм", ATTR_GROUP_SIZE),
    "height-stem": ("Высота до верхнего края штока", "мм", ATTR_GROUP_SIZE),
    "valve-length": ("Длина крана", "мм", ATTR_GROUP_SIZE),
    "valve-od": ("Внешний диаметр крана", "мм", ATTR_GROUP_SIZE),
    "center-to-edge": ("Длина от центра до края крана", "мм", ATTR_GROUP_SIZE),
}

# Normalized label substring / exact → slug (first match wins by specificity order).
_LABEL_RULES: tuple[tuple[str, str], ...] = (
    ("номинальное напряжение", "voltage"),
    ("напряжение питания", "voltage"),
    ("диапазон напряжения", "voltage-range"),
    ("потребляемая мощность", "power-consumption"),
    ("мощность трансформатора", "transformer-va"),
    ("сечение провода", "wire-cross-section"),
    ("сечение подключаемых проводов", "wire-cross-section"),
    ("сигнал управления", "control-signal"),
    ("сигнал обратной связи", "feedback-signal"),
    ("крутящий момент", "moment"),
    ("максимальная площадь заслонки", "damper-area"),
    ("площадь заслонки", "damper-area"),
    ("площадь обслуживаемой заслонки", "damper-area"),
    ("сечение клемм", "terminal-size"),
    ("спецификация терминала", "terminal-size"),
    ("направление вращения", "rotation-direction"),
    ("ручное управление", "manual-override"),
    ("угол поворота", "rotation-angle"),
    ("уровень шума", "noise"),
    ("уровень звуковой мощности", "noise"),
    ("индикация положения", "position-indication"),
    ("вспомогательный переключатель", "aux-switch"),
    ("вспомогательные переключатели", "aux-switch"),
    ("время срабатывания", "running-time"),
    ("время поворота", "running-time"),
    ("датчик температуры", "temp-sensor"),
    ("класс безопасности", "protection-class"),
    ("класс защиты", "protection-class"),
    ("степень защиты корпуса", "ip-rating"),
    ("степень защиты", "ip-rating"),
    # Valve media temp before ambient («рабочая температура» alone).
    ("рабочая температура среды", "media-temp"),
    ("рабочая среда", "medium"),
    ("температура окружающей среды", "ambient-temp"),
    ("рабочая температура", "ambient-temp"),
    ("температура хранения", "storage-temp"),
    ("относительная влажность", "humidity"),
    ("влажность", "humidity"),
    ("испытание на влажность", "humidity"),
    ("габаритные размеры", "dimensions"),
    ("длина вала", "shaft-length"),
    ("размер вала", "shaft-length"),
    ("диаметр вала", "shaft-diameter"),
    ("масса", "weight"),
    ("вес", "weight"),
    ("вид крана", "ways"),
    ("совместимый привод", "compatible-actuators"),
    ("совместимые электроприводы", "compatible-actuators"),
    ("кронштейн", "bracket"),
    ("максимальный рабочий перепад", "diff-pressure"),
    ("перепад давления", "diff-pressure"),
    ("золотниковый шток", "ball-stem-material"),
    ("двойное уплотнение штока", "stem-seal"),
    ("уплотнение корпуса", "seat-seal"),
    ("выпрямительный диск", "flow-disk"),
    ("высота от центра крана до верхнего края привода", "height-actuator"),
    ("высота от центра крана до верхнего края штока", "height-stem"),
    ("длина крана", "valve-length"),
    ("внешний диаметр крана", "valve-od"),
    ("длина от центра до края крана", "center-to-edge"),
    ("резьба внутренняя", "thread"),
    ("резьба", "thread"),
    ("материал корпуса", "material"),
    ("материал", "material"),
)


def _norm_label(label: str) -> str:
    s = " ".join((label or "").casefold().split())
    s = s.replace("ё", "е")
    return s


def label_to_slug(label: str, *, value: str = "") -> str | None:
    """Resolve a Russian ТТХ label to a canonical attribute slug.

    Args:
        label: Left side of ``Label: value`` or Attribute.name.
        value: Optional value (disambiguates «Мощность» → moment if Нм).

    Returns:
        Canonical slug or None if unknown / noise.
    """
    n = _norm_label(label)
    if not n:
        return None
    # Skip section headers / noise.
    if n in {
        "технические характеристики",
        "общие параметры",
        "общие характеристики",
        "общие сведения",
        "электрические параметры",
        "электрические характеристики",
        "функциональные параметры",
        "условия эксплуатации",
        "управление",
        "сигнал обратной связи",
        "принцип работы",
        "производитель",
        "модель",
        "тип",
        "назначение",
        "особенности",
    }:
        # «Управление: 2-/3-позиционное» is a real attr; bare section is not.
        if n == "управление" and value.strip():
            return "control"
        if n == "сигнал обратной связи" and value.strip():
            return "feedback-signal"
        return None

    # «Мощность» often means torque in Tilda.
    if n == "мощность" or n.startswith("мощность "):
        if "нм" in _norm_label(value) or re.search(r"\d", value or ""):
            if "трансформатор" in n:
                return "transformer-va"
            if "потребляем" in n:
                return "power-consumption"
            if "нм" in _norm_label(value):
                return "moment"
        return None

    if n in {"напряжение", "напряжение (в)"}:
        return "voltage"

    if n == "dn" or n.startswith("dn "):
        return "dn"
    if n.startswith("kvs") or n == "kv":
        return "kvs"

    # Longest / most specific rule first (rules already ordered).
    for needle, slug in _LABEL_RULES:
        if n == needle or n.startswith(needle) or needle in n:
            # «Класс защиты: IP54» → степень защиты корпуса.
            if slug == "protection-class" and re.search(
                r"\bip\s*\d",
                _norm_label(value),
            ):
                return "ip-rating"
            return slug

    return None


def canonical_meta(slug: str) -> tuple[str, str, str] | None:
    """Return (name, unit, group) for a canonical slug."""
    return CANONICAL_ATTRS.get(slug)
