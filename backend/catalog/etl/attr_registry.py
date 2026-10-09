"""Canonical Attribute.name / Attribute.unit per slug for catalog ETL.

Every enricher passes its own label; without one registry the public
«Характеристики» label flipped with whichever series ran last
(«Степень защиты» vs «Степень защиты корпуса»). Slugs listed here always
get this name/unit; unlisted slugs keep what Admin or the first writer set.
"""

from __future__ import annotations

from typing import Final

CANONICAL_ATTRS: Final[dict[str, tuple[str, str]]] = {
    "ambient-temp": ("Температура окружающей среды", "°C"),
    "application": ("Применение", ""),
    "aux-switch": ("Вспомогательный переключатель", ""),
    "ball-stem-material": ("Золотниковый шток и шар", ""),
    "bracket": ("Кронштейн", ""),
    "cable-length": ("Длина кабеля", "мм"),
    "charge-time": ("Время зарядки конденсатора", "с"),
    "compatible-actuators": ("Совместимый привод", ""),
    "connection": ("Соединение", ""),
    "control": ("Управление", ""),
    "control-signal": ("Упр. сигнал Y", ""),
    "control-signal-y": ("Упр. сигнал Y", ""),
    "damper-area": ("Площадь заслонки", "м²"),
    "diff-pressure": ("Максимальный рабочий перепад давления", "МПа"),
    "dimensions": ("Габаритные размеры", "мм"),
    "dn": ("DN", ""),
    "drive-kind": ("Подходит для электроприводов", ""),
    "equipment-type": ("Тип оборудования", ""),
    "face-to-face": ("Строительная длина C", "мм"),
    "failsafe-time": ("Время возврата без питания", "с"),
    "fault-alarm": ("Аварийный сигнал", ""),
    "feedback-signal": ("Обратная связь U", ""),
    "feedback-signal-u": ("Обратная связь U", ""),
    "flange-bolts-pn16": ("Болты PN16", ""),
    "flange-bolts-pn25": ("Болты PN25", ""),
    "flange-face": ("Высота фланца f", "мм"),
    "flange-od-pn16": ("Фланец PN16 ØD", "мм"),
    "flange-od-pn25": ("Фланец PN25 ØD", "мм"),
    "flange-pcd-pn16": ("Фланец PN16 D1", "мм"),
    "flange-pcd-pn25": ("Фланец PN25 D1", "мм"),
    "flow-characteristic": ("Расходная характеристика", ""),
    "flow-disk": ("Выпрямительный диск", ""),
    "height": ("Высота H", "мм"),
    "height-actuator": ("Высота до верхнего края привода", "мм"),
    "height-h1": ("Высота H1", "мм"),
    "height-stem": ("Высота до верхнего края штока", "мм"),
    "humidity": ("Относительная влажность", ""),
    "ip-rating": ("Степень защиты корпуса", ""),
    "kvs": ("Kvs", "м³/ч"),
    "leakage": ("Утечка", ""),
    "manual-override": ("Ручное управление", ""),
    "material": ("Материал корпуса", ""),
    "material-plug": ("Материал затвора", ""),
    "material-seal": ("Уплотнительное кольцо", ""),
    "material-seat": ("Материал седла", ""),
    "material-stem": ("Материал штока", ""),
    "media-temp": ("Рабочая температура среды", "°C"),
    "medium": ("Рабочая среда", ""),
    "moment": ("Крутящий момент", "Нм"),
    "noise": ("Уровень шума", "дБ(A)"),
    "notes": ("Примечание", ""),
    "partner-indexes": ("Индексы совместимых моделей", ""),
    "position-indication": ("Индикация положения", ""),
    "power-consumption": ("Потребляемая мощность", "Вт"),
    "pressure-rating": ("Номинальное давление", ""),
    "protection-class": ("Класс защиты", ""),
    "rotation-angle": ("Угол поворота", "°"),
    "rotation-direction": ("Направление вращения", ""),
    "run-time": ("Время срабатывания", ""),
    "running-time": ("Время поворота", "с"),
    "seat-seal": ("Уплотнение корпуса крана", ""),
    "series": ("Серия", ""),
    "shaft-diameter": ("Диаметр вала", "мм"),
    "shaft-length": ("Длина вала заслонки", "мм"),
    "stem-seal": ("Двойное уплотнение штока", ""),
    "storage-temp": ("Температура хранения", "°C"),
    "temp-sensor": ("Датчик температуры", ""),
    "terminal-size": ("Сечение клемм", "мм²"),
    "thread": ("Резьба", ""),
    "transformer-va": ("Мощность трансформатора", "В·А"),
    "valve-length": ("Длина L", "мм"),
    "valve-od": ("Внешний диаметр крана", "мм"),
    "valve-type": ("Тип клапана/крана", ""),
    "voltage": ("Номинальное напряжение", ""),
    "ways": ("Вид крана", ""),
    "weight": ("Масса", "кг"),
    "wire-cross-section": ("Сечение провода", "мм²"),
}


def canonical_label(slug: str, name: str, unit: str = "") -> tuple[str, str]:
    """Return the registry name/unit for ``slug``, else the caller's pair."""
    return CANONICAL_ATTRS.get(slug, (name, unit))
