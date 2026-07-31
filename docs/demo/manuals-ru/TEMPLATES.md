# Шаблоны инструкций (RU A4 × 2)

Канон кода: [`scripts/pptx-manual-to-html.py`](scripts/pptx-manual-to-html.py)
(`VoltageTemplate`, `VOLTAGE_TEMPLATES`, `DiagramProfile`,
`DIAGRAM_PROFILES`, `HTML_SHELL`).

Термины RU: [docs/tech-copy-belimo-ru.md](../../tech-copy-belimo-ru.md).
**Канон данных:** `_инструкции-pdf/` (ТТХ, схемы, aux). PPTX — только
внутренний каркас извлечения, в `manuals-ru/` не публикуется.
Готовые руководства по семействам:
[`DA/`](DA/) (готово), [`SA/`](SA/), [`HV/`](HV/)
(`{DA,SA,HV}/<stem>.html`, `{DA,SA,HV}/assets/<stem>/`).
Curated для генератора / шаблонов: [`assets/`](assets/).
Шаблоны V24/V230 — в корне `manuals-ru/`.

Эталонные HTML-каркасы (пусто / плейсхолдеры):

| Файл | Напряжение |
|------|------------|
| [template-v24.html](template-v24.html) | AC/DC **24 В** |
| [template-v230.html](template-v230.html) | AC **100…240 В** |

---

## Шаблоны по напряжению (новые EN→RU)

Производитель часто отдаёт **отдельные** PDF на 24 В и на 230 В
(пример: `da8_16_24_32mu24-*.pdf` / `da8_16_24_32mu230-*.pdf`,
`da8_16_24mqu24-*.pdf` / `…mqu230-*.pdf`). Для таких серий **не**
склеивать 24|230 в одну таблицу — брать шаблон V24 или V230.

Код: `VOLTAGE_TEMPLATES["v24"|"v230"]`, хелперы
`voltage_template_for_sku` / `voltage_template_for_skus`
(если SKU смешанные 24+230 → `None`, это комбинированный мануал).

### V24 — AC/DC 24 В

| Поле | Значение |
|------|----------|
| Токен в SKU | `24` (`DA…MU24-…`, `DA…FU24-…`) |
| Номинальное напряжение | `AC/DC 24 В, 50/60 Гц` |
| Класс защиты | **III** (безопасное сверхнизкое напряжение) |
| Lead-буллет | `Номинальное напряжение: AC/DC 24 В` |
| Колонки ТТХ | только Nm / исполнения **внутри 24 В** |
| Схемы | кроп из `*24*` PDF (не из 230) |

Чеклист перевода EN→RU:

1. Взять `template-v24.html` + глоссарий Belimo RU.
2. Заполнить SKU, момент, времена, мощность, площадь, IP, вал, массу из PDF.
3. Aux / DIP — углы и клеммы **только** из этого PDF.
4. Materialize wiring / dims / rotation / product из того же `*24*` PDF.
5. Stem: `…24-a-as` / `…24-d-ds` (без `230` в имени).

### V230 — AC 100…240 В

| Поле | Значение |
|------|----------|
| Токен в SKU | `230` |
| Номинальное напряжение | `AC 100…240 В, 50/60 Гц` |
| Класс защиты | **II** (все изолировано / полная изоляция) |
| Lead-буллет | `Номинальное напряжение: AC 100…240 В` |
| Колонки ТТХ | только Nm / исполнения **внутри 230 В** |
| Схемы | кроп из `*230*` PDF (проводка часто другая, чем у 24 В) |

Чеклист — как у V24, stem с `230`.

### Когда не V24/V230

Уже готовые комбинированные руководства (24 В **и** 230 В в одном HTML)
оставляем как есть — см. § «Правило выбора ТТХ» ниже. Новые серии с
раздельными PDF — только V24 **или** V230.

---

## Зафиксированный каркас (не ломать)

| Лист | Сетка | Блоки |
|------|--------|--------|
| **1** | 12 кол., A4 landscape | Hero → **sheet1-body**: cols **1–6** (aux ± схема; Внимание; контакты) \| cols **7–12** (product 7–9 + media-meta 10–12 + doc-title) → foot |
| **2** | 12 кол. | Summary (фото+лид) + **diagrams** справа; **tech-block** ТТХ слева снизу |

Порядок схем на листе 2 (жёстко):

1. Схема подключения (`wiring.png`)
2. Габариты (`dimensions.png`)
3. Вращение / упор (`rotation` — текст cols 7–9; `rotation.png` **10–12**)

Без row-guide / sheet-frame scale / глобального fit-text.
JS-fit: `fitDocTitle()` (заголовок документа) и `fitTorque()` (Nm).

## Лист 1 — media-meta

`.media-meta`: flex column, по центру; длинный `.torque`
(«10 / 15 / 20 Нм») сжимается `fitTorque()` под ширину блока.

## Лист 2 — tech-block

- Таблицы ТТХ в обёртках `.tech-table-slot` с `flex: N 1 0`
  (`N = --tech-rows`) — сами `<table>` во flex не сжались бы.
- Ячейки: плотный padding; нижняя граница не должна обрезаться
  `overflow: hidden` (у слота `padding-bottom: 1px`).

## Лист 2 — diagrams / PDF-ассеты (готовые stems)

| Stem | Источник схем | `rotation_kind` | Картинка вращения |
|------|---------------|-----------------|-------------------|
| `da2mu-d-ds` | **LOCKED готовый** — не пересобирать | `terminals` | да |
| `da2mu-a-as` | **LOCKED готовый** — не пересобирать | `signal` | да |
| `da3fu-d-ds` | **LOCKED готовый** — не пересобирать | `screw` | нет |
| `da4-6mu-d-ds` | **LOCKED готовый** — не пересобирать | `terminals_jumper` | да |
| `da4-6mu-a-as` | **LOCKED готовый** — не пересобирать | `terminals_jumper` | да |
| `da5fu-d-ds` | **LOCKED готовый** — не пересобирать | `angle_limit` | да |
| `da10-15-20fu24-230-d-ds` | **LOCKED готовый** — не пересобирать | `angle_limit` | да |
| `da10-15-20fu24-a-as` | **LOCKED готовый** — не пересобирать | `slider` | да |
| `da8-16-24-32mu24-a-as` | **LOCKED готовый** — не пересобирать | `dip` | DIP table |
| `da8-16-24-32mu24-d-ds` | **LOCKED готовый** — не пересобирать | `commutating` | S1 |
| `da8-16-24-32mu230-a-as` | **LOCKED готовый** — не пересобирать | `dip` | DIP table |
| `da8-16-24-32mu230-d-ds` | **LOCKED готовый** — не пересобирать | `commutating` | S1 |
| `da8-16-24mqu24-a-as` | **LOCKED готовый** — не пересобирать | `dip` | DIP table |
| `da8-16-24mqu230-a-as` | **LOCKED готовый** — не пересобирать | `dip` | DIP table |
| `da8-16-24mqu230-d-ds` | **LOCKED готовый** — не пересобирать | `commutating` | S1 |

**Locked manuals** (`LOCKED_MANUAL_STEMS`): HTML + `{DA,SA,HV}/assets/<stem>/`
не трогать генераторами. Сейчас: **15** DA в `DA/` + **`sa3fu-ds-dst`**,
**`sa5fu-ds-dst`**, **`sa7mu-ds-dst`**, **`sa10fu-ds-dst`**, **`sa10mu-ds-dst`**,
**`sa15fu-ds-dst`**, **`sa15mu-ds-dst`** в `SA/`.
Обход только с `--force`.

**Locked DIP:** `assets/dip-diagram-control-signal-ru.png` (Creator Studio,
белый фон). Генератор только копирует в `DA/assets/<stem>/dip-diagram.png`;
SHA256 зафиксирован в `DIP_DIAGRAM_LOCKED_SHA256` — смена файла без обновления
digest → ошибка. Не кропать из EN PDF.

`angle_limit` (DA5FU, DA10/15/20 FU D/DS): баннер и текст про **механический упор угла**,
не «переключение направления»; схема — винт ограничения из PDF.
У `da10-15-20fu24-230-d-ds` лист 1 — `sheet1_aux_diagram` из PDF стр. 3.

`slider` (DA10/15/20 FU24 A/AS): баннер «Изменение положения ручки
переключателя»; схема крышки с ползунком направления; лист 1 —
`sheet1_aux_diagram` (S1…S6) из PDF стр. 3. Источники 15/20 Nm —
`da15fu24-a:as.pdf` / `da20fu24-a:as.pdf` (те же блоки схем).

PDF-кропы (`_pdf_clip_png`):

- после клипа — `_trim_white`;
- у **габаритов** — `crop_bottom_banner=True` (срезать тёмную полосу /
  баннер следующей секции снизу кадра);
- при необходимости зеркально: `_crop_dark_title_banner` для catalog webp.

`da4-6mu-d-ds` / `da4-6mu-a-as`: лист 1 — `sheet1_aux_diagram` из PDF;
у A/AS ещё `sheet1_dip_diagram`.

## Текст

Глоссарий Belimo RU обязателен. Баннеры схем — из профиля
(`_rotation_figure_html`), не хардкод «направление вращения» для всех.

## Правило выбора ТТХ (готовые / комбинированные)

| Условие по SKU в руководстве | Шаблон колонок |
|------------------------------|----------------|
| **Один** Nm, 24 В + 230 В в одном HTML | 2 колонки **24 В \| 230 В** |
| **Один** Nm, только V24 или только V230 | 1 колонка (шаблон V24/V230) |
| **Два и больше** Nm | **per_sku** (при необходимости схлоп 15+20) |

### Комбинированные 24+230 (legacy)

| Stem | SKU |
|------|-----|
| `da2mu-d-ds` | DA2MU24-D/DS, DA2MU230-D/DS |
| `da2mu-a-as` | DA2MU24-A/AS, DA2MU230-A/AS |
| `da3fu-d-ds` | DA3FU24-D/DS, DA3FU230-D/DS |
| `da5fu-d-ds` | DA5FU24-D/DS, DA5FU230-D/DS |
| `da4-6mu-d-ds` | DA4/6 MU 24/230 D/DS |
| `da4-6mu-a-as` | DA4/6 MU 24/230 A/AS |
| `da10-15-20fu24-230-d-ds` | DA10/15/20 FU24+FU230 D/DS |

### Только 24 В (пример готового)

| Stem | SKU |
|------|-----|
| `da10-15-20fu24-a-as` | DA10/15/20 FU24 A/AS |

Для DA10/15/20 колонки **15+20 Нм** (одного напряжения) схлопываются в
`DA15/20…` со значениями через слеш, если различаются.

## Очередь EN (ориентир на V24 / V230)

Раздельные PDF в `_инструкции-pdf/EN/` — один PDF → один HTML
в папке семейства (`DA/` / `SA/` / `HV/`).

### DA/ — готово (locked)

| Stem | PDF | Шаблон |
|------|-----|--------|
| `da8-16-24-32mu24-a-as` | `da8_16_24_32mu24-a_as.pdf` | V24 |
| `da8-16-24-32mu24-d-ds` | `da8_16_24_32mu24-d_ds.pdf` | V24 |
| `da8-16-24-32mu230-a-as` | `da8_16_24_32mu230-a_as.pdf` | V230 |
| `da8-16-24-32mu230-d-ds` | `da8_16_24_32mu230-d_ds.pdf` | V230 |
| `da8-16-24mqu24-a-as` | `da8_16_24mqu24-a_as.pdf` | V24 |
| `da8-16-24mqu230-a-as` | `da8_16_24mqu230-a_as.pdf` | V230 |
| `da8-16-24mqu230-d-ds` | `da8_16_24mqu230-d_ds.pdf` | V230 |

Нет в EN: `da8_16_24mqu24-d_ds.pdf`.  
`da5mqu-*.pdf` — комбинированные 24+230 (не V24/V230) — отдельно.

### SA/ — готово (EN→RU, dual 24+230)

| Stem | PDF EN | Статус |
|------|--------|--------|
| `sa3fu-ds-dst` | `sa3fu-ds_dst.pdf` | **LOCKED** |
| `sa5fu-ds-dst` | `sa5fu-ds_dst.pdf` | **LOCKED** |
| `sa10fu-ds-dst` | `sa10fu-ds_dst.pdf` | **LOCKED** |
| `sa15fu-ds-dst` | `sa15fu-ds_dst.pdf` | **LOCKED** |
| `sa7mu-ds-dst` | `sa7mu-ds_dst.pdf` | **LOCKED** (только DS) |
| `sa10mu-ds-dst` | `sa10mu-ds_dst.pdf` | **LOCKED** (только DS) |
| `sa15mu-ds-dst` | `sa15mu-ds_dst.pdf` | **LOCKED** (только DS) |
| `sa30mu-ds-dst` | `sa30mu-ds_dst.pdf` | **LOCKED** (только DS) |

Комбинированный 24+230 в одном PDF (не V24/V230).
SAFU — DS/DST + блок SAF72; **SAMU — только DS** (без DST).

### HV/ — очередь (папка готова)

| Ориентир stem | PDF EN |
|---------------|--------|
| `hva-2` | `hva-2.pdf` |
| `hva-5` | `hva-5.pdf` / `HVA-5 instruction.pdf` |
| `hva-5q` | `hva-5q.pdf` |
| `hva-5uq` | `hva-5uq.pdf` |
| `hva-8q` | `hva-8q.pdf` |
| `hva-10` | `hva-10.pdf` |
| `hva-10q` | `hva-10q.pdf` |
| `hva-20` | `hva-20.pdf` |
| `hva-20q` | `hva-20q.pdf` |
| `hva-40` | `hva-40.pdf` |
| `hva-40q` | `hva-40q.pdf` |
| `hvd-3f-s-st` | `hvd-3f-s_st.pdf` |
| `hvd-5f-s-st` | `hvd-5f-s_st.pdf` |

Пересборка EN→RU:

```bash
python3 docs/demo/manuals-ru/scripts/en_pdf_to_manuals.py
```

## Кроп фото (печать PDF)

В тулбаре мануала — **«Кроп фото»** ([`assets/photo-crop-tool.js`](assets/photo-crop-tool.js)):

1. Цель: `product` (лист 1) или `lead` (лист 2).
2. Слайдеры границ (верх / право / низ / лево, %).
3. `clip-path` применяется **и на экране, и в «Печать / PDF»** (панель скрывается, кроп остаётся).
4. Чтобы запечь в файл: **Скачать PNG** → заменить `assets/<stem>/product.png` или `lead.png` → **Сброс**.

Открывать через `http.server` (не `file://`), иначе скачивание PNG может упереться в CORS.

---

## Пересборка

```bash
python3 docs/demo/manuals-ru/scripts/pptx-manual-to-html.py
```

Пишет готовые HTML в `{DA,SA,HV}/` по семейству stem, шаблоны
`template-v24.html` / `template-v230.html` в корень.
Превью: эта папка (локально часто `python3 -m http.server 8765`).
