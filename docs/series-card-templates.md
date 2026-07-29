# Шаблоны карточек по сериям

Дата: 2026-07-24  
Статус: **канон** для сборки карточек Product/SKU (ETL и ручной ввод в Admin).

> Когда меняем поведение карточки серии на сайте — **сначала** обновляем
> этот документ, затем код.

Цель: быстро собрать карточку «как у уже работающей серии» — со всеми
осями PDP, collapse в каталоге, фасетами и RFQ-китом (где нужно).

Связанный код (источник истины в рантайме):

| Слой | Файлы |
|------|--------|
| Collapse list | `backend/catalog/family_cards.py`, `frontend/src/utils/h81CatalogCollapse.ts` |
| Siblings / picker | `backend/catalog/siblings.py`, `frontend/src/components/SkuVariantPicker.tsx` |
| Soft-nav overlay | `frontend/src/utils/skuSiblingOverlay.ts`, `SkuDetailPage.tsx` |
| RFQ kit (корпуса) | `backend/catalog/ball_valve_kit.py`, `BallValveKitFields.tsx` |
| Категории | `backend/catalog/series_categories.py` |
| Фасеты | `backend/catalog/facets/defs.py` |
| ETL | `etl/series_copy_{damu,samu,ball_valves}.py`, `etl/h81_kits.py`, `etl/h8205_lav.py` |

Общая модель: **Category → Product (линейка) → SKU (артикул/издание)**.
На PDP всегда открывается **SKU**; у семейных серий picker переключает
siblings на том же Product.

---

## Сводка

| Серия | Product = | Collapse в каталоге | Категория | Оси picker | RFQ «добавить привод» |
|-------|-----------|---------------------|-----------|------------|------------------------|
| **DA\*** (DAMU) | 1 Nm-линейка | **да** | без пружины | V / управление (A/AS/D/DS) | нет |
| **SA\*** (SAMU) | 1 Nm-линейка | **да** | дымоудаление | V / управление (DS/DST) | нет |
| **SA\*FU** (SAFU) | 1 Nm-линейка | **да** | противопожарные | V / управление (DS/DST) | нет |
| **HVA** | 1 Nm-линейка | **да** | без пружины / ускоренные | V / управление (A/AS) | нет |
| **HVD** (воздух) | 1 Nm/Q-линейка | **да** | без пружины | V / управление (D/DS) | нет |
| **HVD-F** (дым) | 1 NmF-линейка | **да** | дымоудаление | V / управление (DS/DST) | нет |
| **8100** (BV) | 1 DN-серия | да | шаровые краны | Kvs (+ body) | **да** |
| **H8101–H8122** | 1 префикс комплекта | да | комплекты | ways/DN/Kvs/body/V/ctrl | нет |
| **H8205** (LAV) | 1 корпус LAV | да | комплекты | ways/DN/body/V/ctrl(+M) | нет |

**Collapse** включается только если `product.slug` матчит
`is_collapsible_family_product_slug()` (`family_cards.py` + зеркало на FE).
Неверный slug → десятки плиток одной линейки в сетке.

---

## Общий чеклист (любая серия)

В Admin или через ETL:

1. **Category** — канонический slug из таблицы серии (не создавать дубли).
2. **Product** — `name`, `slug` по шаблону серии, `is_published`, тексты линейки
   (description / instructions при необходимости).
3. **SKU** (каждое издание):
   - `sku_code` по шаблону артикула;
   - `slug` по шаблону ЧПУ;
   - `product` = Product линейки;
   - `is_published`, `stock_qty` / остатки 1С;
   - ТТХ: AttributeValue (slug атрибутов как у референса);
   - фото (`ProductImage`), PDF (`ProductFile`).
4. Проверка на сайте:
   - карточка в нужной категории;
   - для семейных — **одна** плитка на Product; в сетке — «N вариантов» и
     CTA «Выбрать вариант» (`edition_count` в list API);
   - PDP: picker (если >1 издания), highlights, вкладка «Характеристики», RFQ;
   - для 8100 — чекбокс «Добавить электропривод» в RFQ.

Терминология ТТХ: [tech-copy-belimo-ru.md](tech-copy-belimo-ru.md).

---

## 1. DA\* — воздушные без пружины (DAMU)

### Замысел карточки

**Одна плитка на Nm** (DA2MU…DA32MU). Электрические издания
(24/230 × D/DS/A/AS) — siblings на том же Product; на PDP — picker
напряжения и управления.

### Идентификаторы

| Поле | Шаблон | Пример |
|------|--------|--------|
| Category.slug | `elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata` | — |
| Product.slug | `privod-vozdushniy-bez-pruzhini-damu-{n}nm` | `…-damu-8nm` |
| Product.name | `DA{n}MU \| Электропривод воздушный без возвратной пружины, {n} Нм` | — |
| SKU.sku_code | `DA{n}MU{24\|230}-{D\|DS\|A\|AS}` | `DA8MU24-D` |
| SKU.slug | обычно legacy/Tilda + издание (не ломать 301) | см. SEO-карту |

Не путать с **DAMQU** / **HVA** (другие шаблоны slug; HVA — свой § ниже).

**DAMQU** (ускоренные без пружины): Product.slug
`privod-vozdushniy-da{n}mqu-{n}nm` (5/8/10/20 Нм), категория
`elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata`, collapse BE+FE
`da\d+mqu`. Ensure gaps: `ensure_ai_catalog_gaps`.

**DAEU** (электронные отказоустойчивые) — снята с производства, в РФ-каталог
не входит.

### ТТХ / highlights (минимум)

moment, damper-area, voltage, control, aux_switch (для \*-S), running-time,
ip-rating, габариты/вес/вал — как у референса после `enrich_damu`.

### Каталог / PDP

- Collapse: **да** (`privod-vozdushniy-bez-pruzhini-damu-\d+nm`).
- List title: **Product.name** (серия Nm), representative `sku_code`
  (предпочтение изданиям **в наличии**; иначе первый по `sku_code`).
- Фасеты: полный набор приводов (`FACET_DEFS`); фильтр → затем одна плитка.
- Picker: напряжение, управление (A/AS/D/DS).
- Soft-nav + overlay voltage/control.
- `ball_valve_kit`: нет.

### Сборка вручную (Admin)

1. Product в категории «без пружины», slug `privod-vozdushniy-bez-pruzhini-damu-{n}nm`.
2. На каждое издание — SKU с кодом `DA…`, **тот же** Product, published.
3. AttributeValue как у соседнего DA той же Nm (скопировать набор, поменять
   voltage/control/aux).
4. PDF инструкции серии + фото.
5. Опционально: `analog_belimo_code`, остатки.

### ETL

```bash
poetry run python manage.py enrich_damu
poetry run python manage.py attach_manual_pdfs --series damu
```

Код: `backend/catalog/etl/series_copy_damu.py`.

### Референс

Product `privod-vozdushniy-bez-pruzhini-damu-8nm`, артикул `DA8MU24-D`
(8 siblings на PDP).

### Если меняем карточку DA

Обновить: enricher attrs/highlights, `parse_sku_variant` / torque specs,
фасеты приводов, collapse allowlist (BE+FE), этот §1, при необходимости SEO URL.

---

## 2. SA\* — дымоудаление (SAMU)

### Замысел

**Одна плитка на Nm**. Издания 24/230 × **DS / DST** (терморазмыкатель) —
siblings; picker различает DST отдельным ключом управления.

### Идентификаторы

| Поле | Шаблон | Пример |
|------|--------|--------|
| Category.slug | `elektroprivody-dlya-klapanov-dymoudaleniya` | — |
| Product.slug | `privod-dimoudaleniya-{n}nm` | `privod-dimoudaleniya-10nm` |
| Product.name | `SA{n}MU \| Электропривод дымового клапана без возвратной пружины, {n} Нм` | — |
| SKU.sku_code | `SA{n}MU{24\|230}-{DS\|DST}` | `SA10MU24-DST` |

Моменты в каноне enricher: 7 / 10 / 15 / 30 Нм (`TORQUE_SPECS` в samu).

### ТТХ

moment, area, voltage, control (on/off), aux (2×SPDT), **temp_sensor=SAF72**
для `-DST` (иначе «Нет»), runtime, вес, вал.

### Каталог / PDP

- Collapse: **да** (`privod-dimoudaleniya-\d+nm`).
- List title: Product.name; фасеты приводов.
- Picker: напряжение, управление **DS / DST** (`siblings.sibling_edition_row`
  через `sku_code_is_thermal`).
- Soft-nav + overlay; RFQ kit нет.

### Сборка вручную

Аналогично DA, категория дымоудаления, коды `SA…`, все издания на одном
Product. Не смешивать SKU SA и DA на одном Product.

### ETL

```bash
poetry run python manage.py enrich_samu
poetry run python manage.py attach_manual_pdfs --series samu
```

Код: `backend/catalog/etl/series_copy_samu.py`.

### Референс

Product `privod-dimoudaleniya-10nm`; `SA10MU24-DS` / `SA10MU24-DST`.

### Если меняем карточку SA

§2 + `series_copy_samu.py` + thermal helpers + collapse allowlist (BE+FE).

---

## 2a. SA\*FU — противопожарные с пружинным возвратом (SAFU)

### Замысел

**Одна плитка на Nm** (SA3FU…SA20FU). Издания 24/230 × **DS / DST** —
siblings; picker различает DST через `sku_code_is_thermal`.

### Идентификаторы

| Поле | Шаблон | Пример |
|------|--------|--------|
| Category.slug | `elektroprivody-protivopozharnye-i-dymovye` | — |
| Product.slug | `privod-protivopozharniy-{n}nm` | `privod-protivopozharniy-3nm` |
| Product.name | `SA{n}FU \| Электропривод противопожарного клапана…` | — |
| SKU.sku_code | `SA{n}FU{24\|230}-{DS\|DST}` (в БД часто lower) | `sa3fu230-dst` |

### Каталог / PDP

- Collapse: **да** (`privod-protivopozharniy-\d+nm`).
- List title: Product.name (не «sa3fu230-ds \| …»).
- Picker: напряжение, управление **DS / DST**.
- Soft-nav + overlay; RFQ kit нет.

### ETL

```bash
poetry run python manage.py enrich_safu
```

Код: `backend/catalog/etl/series_copy_safu.py`.

### Референс

`privod-protivopozharniy-3nm`; `sa3fu24-ds` / `sa3fu24-dst`.

---

## 2b. HVA — воздушные без пружины (пропорциональные / ускоренные)

### Замысел

**Одна плитка на линейку** (HVA-5…40, HVA-5Q…40Q). Издания 24/230 ×
**A / AS** — siblings; picker напряжения и управления.

### Идентификаторы

| Поле | Шаблон | Пример |
|------|--------|--------|
| Category.slug | `elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata` или `elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata` | — |
| Product.slug | `privod-vozdushniy-hva-{n}nm` / `privod-vozdushniy-bez-pruzhini-uskorenniy-hva-q-{n}nm` | `…-hva-10nm` |
| SKU.sku_code | `HVA{24\|230}[S]-{n}[Q]` | `HVA24S-10`, `HVA230-20Q` |

Линейки в каталоге 2025 (модулирующие): **5 / 10 / 20 / 40** и ускоренные
**5Q / 10Q / 20Q / 40Q**. Seed: `manage.py enrich_hva --with-media`.

### Каталог / PDP

- Collapse: **да** (оба slug-шаблона выше).
- Picker: V, управление **A / AS** (`parse_sku_variant` → modulating).
- Soft-nav + overlay; RFQ kit нет.

### Референс

`privod-vozdushniy-hva-5nm` / `HVA24-5`; ускоренный —
`privod-vozdushniy-bez-pruzhini-uskorenniy-hva-q-5nm`.

### Связанные HV-линейки (каталог 2025)

| Серия | Product.slug | SKU | Команда |
|-------|--------------|-----|---------|
| HVD-Q | `privod-vozdushniy-hvd-{n}q` | `HVD{24\|230}[S]-{n}Q` | `enrich_hv_extra` |
| HV*QX | `privod-vozdushniy-kondensator-{hva\|hvd}-{n}qx` | `HV{A\|D}{24\|230}[S]-{n}QX` | `enrich_hv_extra` |

HVA-P (пружина, китайский рынок) в РФ-каталог не входит.

Медиа: студийные WebP из HV seria (длинная сторона ≤1600); если нет —
кадр из каталога 2025 при `min_edge ≥ 800`. Дубли героя (Tilda + local)
чистить: `manage.py audit_optimize_product_images`.

---

## 2c. HVD — воздух (on/off) и дым HVD-F

### Замысел

**Одна плитка на линейку момента.** Воздух: 24/230 × **D / DS** (S = aux).
Дым (пружинный F): 24/230 × **DS / DST** (ST = терморазмыкатель).

### Идентификаторы

| Серия | Product.slug | SKU.sku_code |
|-------|--------------|--------------|
| HVD воздух | `privod-vozdushniy-hvd-{n}nm` / `…-hvd-{n}q` | `HVD{24\|230}[S]-{n}[Q]` |
| HVD-F дым | `privod-dimoudaleniya-hvd-{n}f` | `HVD{24\|230}S[T]-{n}F` |

Категории: воздух — без пружины; F — дымоудаление (не путать с SAMU
`privod-dimoudaleniya-\d+nm` — отдельный regex).

### Каталог / PDP

- Collapse: **да** (air + smoke slug-шаблоны).
- Picker воздух: V, **D / DS**; дым F: V, **DS / DST** (`sku_code_is_thermal`).
- Soft-nav + overlay; RFQ kit нет.

### Референс

`privod-vozdushniy-hvd-5nm` / `HVD24-5`; дым —
`privod-dimoudaleniya-hvd-3f` / `HVD24ST-3F`.

---

## 3. 8100 — латунные шаровые (корпуса BV\*)

### Замысел

**Одна карточка на DN** (например вся линейка BV215). Издания A/B/C/… —
это **Kvs** на одном Product; picker меняет Kvs без ухода с «семейной»
карточки. В RFQ — опция подобрать привод + кронштейн.

### Идентификаторы (критично для collapse)

| Поле | Шаблон | Пример |
|------|--------|--------|
| Category.slug | `sharovye-krany` | — |
| Product.slug | `8100-bv{num}` | `8100-bv215` |
| Product.name | `BV{num} \| Шаровой кран {ways} DN {dn}` | `BV215 \| … DN 15` |
| SKU.sku_code | `8100-bv{num}{letter}` | `8100-bv215a` |
| SKU.slug | `{product_slug}-{sku_code}` | `8100-bv215-8100-bv215a` |
| Body (meta) | `BV{num}{LETTER}` | `BV215A` |

Legacy Product `sharovoy-kran-bv*` → 301 на `8100-bv*` (ETL merge).

### ТТХ / highlights

dn, ways, **kvs**, material, thread, габариты, **compatible-actuators**,
**bracket**. Карточка в сетке: dn / ways / kvs / material.

### Каталог / PDP

- Collapse: **да** (`8100-bv\d+`).
- List title: **Product.name** (серия), в карточке виден representative
  `sku_code` (min code среди отфильтрованных).
- Фасеты категории **только**: dn → ways → kvs → material
  (`BALL_VALVE_8100_FACET_KEYS`).
- Picker: Kvs (+ body, если различается); ways/DN обычно одно значение.
- Soft-nav: URL + overlay Kvs/артикула до ответа API.
- **`ball_valve_kit`**: да (только «голый» BV, не H81/H8205). Нужен текст
  Attribute `compatible-actuators`.

### Сборка вручную (новый DN или новая буква Kvs)

**Новый DN (новая плитка):**

1. Category `sharovye-krany`.
2. Product slug строго `8100-bv{num}`, name с DN/ways.
3. SKU на каждую букву Kvs: code `8100-bv{num}a…`, slug
   `8100-bv{num}-8100-bv{num}a`, все на этот Product.
4. AttributeValue: dn, ways, kvs, material, compatible-actuators, bracket, …
5. Проверить: в `/catalog/sharovye-krany` одна плитка; PDP — select Kvs;
   RFQ — «Добавить электропривод».

**Новое издание Kvs на существующем DN:** только новый SKU на тот же Product
+ attrs (kvs) + published. Meta Kvs должна совпасть с таблицей
`BRASS_KIT_BODIES` / `body_meta_for_brass` — иначе picker/siblings покажут
пустое Kvs.

### ETL

```bash
poetry run python manage.py enrich_ball_valves
# точечно:
poetry run python manage.py enrich_ball_valves --series BV220
# герои DN из media-webp (2-WAY/3-WAY BRASS DNxx.webp):
poetry run python manage.py attach_ball_valve_media_webp
# паспорт серии PDF в Документы (без кропов в галерею):
poetry run python manage.py attach_8100_catalog_media
```

Код: `series_copy_ball_valves.py` (`product_slug_for_series`,
`brass_sku_slug`, `merge_brass_bv_onto_dn_products`);
фото — `ball_valve_media_webp.py`; паспорт —
`ball_valve_8100_catalog_media.py` (только ProductFile).

### Референс

Product `8100-bv215`; SKU `8100-bv215a` → slug `8100-bv215-8100-bv215a`.

### Если меняем карточку 8100

Обновить §3 + `family_cards` / FE collapse regex + facets
`BALL_VALVE_8100_FACET_KEYS` + `ball_valve_kit` + overlay + picker axes.

---

## 4. H8101–H8122 — заводские комплекты кран+привод

### Замысел

**Одна карточка на префикс комплекта** (H8101, H8103, …). Все корпуса ×
электрические издания — siblings. В каталоге видна серия (скорость/тип),
на PDP — полный picker (DN, Kvs, корпус, 24/230, A/AS/D/DS).

### Идентификаторы

| Поле | Шаблон | Пример |
|------|--------|--------|
| Category.slug | `komplekty` | — |
| Product.slug | `h81{xx}` lowercase | `h8101`, `h8122` |
| Product.name | `H81{xx} \| Электрический шаровой кран (… серия)` | см. `h81_family_product_name` |
| SKU.sku_code | `H81{xx}-{BODY}-{24\|230}{A\|AS\|D\|DS}` | `H8101-BV215A-24AS` |
| SKU.slug | `{product}-{code lower}` | `h8101-h8101-bv215a-24as` |

Допустимые Product.slug для collapse: **h8101–08, h8121, h8122**
(`H81_FAMILY_PRODUCT_SLUGS`). Новый префикс (например H8109) **не**
схлопнется, пока не добавлен в `family_cards.py` + FE regex + `h81_kits.py`.

Матрицы тел: `KIT_FAMILIES`, `BRASS_KIT_BODIES`, flanged rows в
`etl/h81_kits.py`.

### ТТХ

Как у комплекта: dn, ways, kvs, body, voltage, control, aux; плюс серийный
copy. List title = Product.name.

### Каталог / PDP

- Collapse: да.
- Фасеты: полный `FACET_DEFS` (категория komplekty без узкого override).
- Picker: ways, DN, Kvs, корпус, напряжение, управление.
- `ball_valve_kit`: **нет** (привод уже в комплекте).

### Сборка вручную

1. Product `h81xx` в `komplekty`, имя серии.
2. SKU только с валидным разбором `parse_h81_kit_parts` — иначе siblings
   без dn/kvs.
3. Не класть H81-SKU на Product `8100-bv*` и наоборот.
4. Медиа/PDF: `attach_manual_pdfs --series h81` / catalog media helpers.

Практичнее: прогон ETL на семью, чем ручной ввод 288 SKU.

### ETL

```bash
poetry run python manage.py enrich_ball_valves
poetry run python manage.py attach_manual_pdfs --series h81
```

### Референс

`h8101` / `H8101-BV215A-24A`; фланцевый `h8103` / `H8103-BV265-24A`.

### Если меняем карточку H81

§4 + `h81_kits.py` + collapse allowlist + siblings + media/stock keys.

---

## 5. H8205 — регулирующие LAV (серия 82)

### Замысел

**Одна карточка на корпус LAV** (LAV232, LAV280, …) = 22 плитки.
На каждой — до 24 электрических изданий (24/230 × A/D/M × опции S/T/ST).

### Идентификаторы

| Поле | Шаблон | Пример |
|------|--------|--------|
| Category.slug | `komplekty` | — |
| Product.slug | `h8205-{body}` | `h8205-lav232` |
| Product.name | `H8205-LAV{…} \| Электрический регулирующий клапан … DN …` | — |
| SKU.sku_code | `H8205-LAV{body}{opts}-{24\|230}{A\|D\|M}` | `H8205-LAV232-24A`, `…LAV280ST-230A` |
| SKU.slug | `{product_slug}-{sku_code.lower()}` | `h8205-lav232-h8205-lav232-24a` |

Список тел: `LAV_BODY_ROWS` / `all_h8205_series()` в `etl/h8205_lav.py`.

### ТТХ

Материалы/фланец PN, расходная характеристика, утечка, voltage/control;
aux/fault из опций S/T/ST. **Kvs не ось siblings** для LAV (в отличие от
8100/H81).

### Каталог / PDP

- Collapse: да (`h8205-lav\d+[st]*` на product slug без ST — ST только в
  артикуле).
- Picker: ways, DN (фиксированы на карточке), body, V, control (**M**
  включён).
- `ball_valve_kit`: нет.

### Сборка вручную

1. Product `h8205-lav{…}` в komplekty.
2. SKU с кодами из `h8205_edition_sku_codes` — иначе parse/siblings пустые.
3. Медиа: общий WebP + slice PDF (`h8205_catalog_media.py`).

Предпочтительно ETL `--series H8205`.

### ETL

```bash
poetry run python manage.py enrich_ball_valves --series H8205
```

### Референс

`h8205-lav232` / `H8205-LAV232-24A`; опции `H8205-LAV280ST-230A`,
`H8205-LAV3300T-24M`.

### Если меняем карточку H8205

§5 + `h8205_lav.py` + collapse regex + catalog media + stock_import keys.

---

## Новая серия (не из таблицы)

1. Выбрать ближайший шаблон (привод / корпус / комплект).
2. Зафиксировать Product.slug-схему **до** массового ввода.
3. Если нужна одна плитка на много SKU — добавить slug в
   `family_cards.py` **и** `h81CatalogCollapse.ts`.
4. Парсер siblings (`siblings.py` + etl parse) — иначе picker пустой.
5. Фасеты: либо общий `FACET_DEFS`, либо override в `CATEGORY_FACET_KEYS`.
6. Добавить **новый §** в этот файл + строку в сводную таблицу.
7. Референс-SKU и pytest на collapse/siblings.

---

## Матрица «куда править код»

| Изменение UX | Backend | Frontend | Этот doc |
|--------------|---------|----------|----------|
| Collapse / одна плитка | `family_cards.py` | `h81CatalogCollapse.ts` | сводка + § серии |
| Оси picker / siblings | `siblings.py`, etl parse | `SkuVariantPicker`, `skuVariantResolve` | § серии |
| Soft-nav ТТХ | — | `skuSiblingOverlay`, `SkuDetailPage` | shared plumbing |
| RFQ kit привода | `ball_valve_kit.py` | `BallValveKitFields` | §8100 |
| Фасеты категории | `facets/defs.py` | CatalogPage (косвенно) | § серии |
| ТТХ / copy | `series_copy_*.py` | — | § серии + tech-copy |
| List title семейной | `serializers.get_name` | — | сводка |
| Счётчик вариантов | `edition_count` annotate + serializer | `CatalogSkuCard`, `editionCountLabel` | чеклист |

---

## Приёмка (smoke)

| Серия | URL / проверка |
|-------|----------------|
| DA | `/catalog/…bez-pruzhinnogo…` — **7** плиток DA\*MU (по Нм); «8 вариантов» + CTA «Выбрать вариант»; PDP picker V/ctrl |
| SA | дымоудаление — **3** плитки SA\*MU; N вариантов + CTA; PDP DS/DST |
| SA\*FU | противопожарные — **5** плиток (3/5/10/15/20 Нм); N вариантов + CTA; PDP DS/DST |
| HVA | без пружины — плитки HVA-5/10/20/40; ускоренные — HVA-5Q…40Q; PDP A/AS |
| HVD | без пружины — по **1** плитке HVD-5/10/20/40Q; PDP D/DS |
| HVD-F | дымоудаление — **2** плитки (3F/5F); PDP DS/DST |
| 8100 | `/catalog/sharovye-krany` — одна плитка на DN; N вариантов + CTA; PDP Kvs; RFQ kit |
| H81 | `/catalog/komplekty` — по одной плитке H8101…; N вариантов + CTA; PDP много осей |
| H8205 | komplekty — 22 LAV-плитки; PDP 24/230 A/D/M |
