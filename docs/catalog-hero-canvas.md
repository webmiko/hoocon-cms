# Герои каталога: общий canvas и относительный размер

Дата: 2026-07-30  
Статус: **канон** для cutout-фото в карточке / PDP (после brass + HV).

Цель: в сетке каталога изделия одной семьи читаются в одном визуальном
масштабе (DN / Нм), без обрезки и без «двойного» уменьшения (asset + CSS).

---

## Принцип

1. **Один portrait-холст** на семью (сейчас **1661×2076**).
2. **Поля ~7%** (`MARGIN = 0.07`) — полезный кадр внутри.
3. **Размер ∝ оси семьи**, сжатая кривая как у HV в FE:
   `factor = 0.75 + 0.25 * min(value, REF) / REF`
   - brass: `value = DN`, `REF = 50` → DN15 ≈ 0.825, DN50 = 1.0
   - HVA/HVD air: `value = Нм`, `REF = 40` → 5 ≈ 0.78, 40 = 1.0
   - HVD-…F: `value = Нм`, `REF = 5` → 3 ≈ 0.90, 5 = 1.0
   - DA/SA: `value = max(Nm в stem)`, `REF = 32` → DA2 ≈ 0.77, SA30 ≈ 0.98
     (один файл на 8/16/24 — один размер корпуса; DA32 reuse DA24 pack)
   - H81 / H8205: **без кривой DN** — одно studio-фото на семью; только
     trim + center на полный inner-box (`center_cutout_on_canvas`)
4. **Метрика масштаба — длинная сторона** content-bbox (не «сырой» scale
   пикселей разных исходников). Иначе «плоский» DN50/40Nm выглядит мельче
   плотного DN40.
5. **Центр** cutout на холсте после trim alpha / near-white.
6. **FE:** для запечённых героев `target = 1`, `maxCssScale = 1`
   (`isHvCanvasMediaSku` / `isDaSaCanvasMediaSku` / DN highlights).
   Не масштабировать второй раз.
7. **CSS:** у `valve` / `air` / `smoke` / `fire` — без `--media-pad-inline: 40px`
   (поля уже в WebP). Fit через `max-width/height` + `object-fit`, не
   `transform: scale` (иначе клип).

**Не** один проход на весь каталог: ось и pack свои на семью; общий только
стиль (холст + иерархия + fit).

---

## Pack

| Семья | Источник | Stem / имена | Attach |
|-------|----------|--------------|--------|
| Brass 8100 | Yandex `…/media-webp/` | `2-WAY BRASS DNxx.webp`, `3-WAY …` | `attach_ball_valve_media_webp` |
| HVA/HVD air | тот же `media-webp/` | `hva-5.webp` … `hvd-40qx.webp` | `attach_hv_media_webp` |
| HVA/HVD per-SKU | Yandex `弹簧复位产品/` | perspective PNG; else frontal PNG/TIFF | `attach_hv_sku_media` |
| HVD-…F | PDF manuals → ETL | `hvd-{3,5}f-photo(.webp)` | `attach_manual_diagrams --series hvdf` |
| DA/SA | тот же `media-webp/` | `da8:16:24mu24-d:ds.webp`, `sa5fu-ds.webp`, … | `attach_da_sa_media_webp` |
| H81 / H8205 | JPEG embeds каталога шаровых | `img_0019…` / `img_0024…` | `attach_manual_diagrams --series h81` + `enrich_ball_valves` (H8205) |

Локальный root:

```text
~/Yandex.Disk.localized/фото для сайта/media-webp/
```

VPS (в контейнере):

```text
/app/media/_pack/media-webp/   ← хост: /var/www/hoocon/media/_pack/media-webp/
```

Перед правкой pack: бэкап в `/tmp/*-canvas-bak` (не перезаписывать bak
повторным прогоном поверх уже сжатых файлов).

---

## Алгоритм offline-normalize (brass / HV)

Повторяемый скрипт (ad-hoc `poetry run python`, не management command):

1. Скопировать исходники в bak (один раз).
2. `load_cutout`: open → (JPG: punch white) → content bbox → crop.
3. Взять **REF**-кадры (DN50 / все `*-40*.webp`), вписать в inner-box,
   `ref_long = max(fitted w, fitted h)` (для HV — max по всем 40 Нм).
4. Для каждого файла: `target_long = ref_long * factor(value)`;
   `scale = target_long / max(cw, ch)`; clamp в inner; paste по центру.
5. Save WebP (`DEFAULT_WEBP_QUALITY`, `WEBP_METHOD`).
6. Превью в `/tmp/*-canvas-preview` по желанию.
7. **Только локально** проверить каталог (hard-refresh / сброс blob).
8. На VPS — **только после «финал»**: rsync pack → attach.

DN50 brass: предпочтительно свежий **JPG** (punch), не уже сжатый webp из bak.

---

## HVD-…F (дым)

Не media-webp: кроп из English manual (`crop_hvdf_product_photos` +
`punch_near_white_background`).

Проблема S-изданий: справа пад под SAF72 → после punch пустота справа,
фото «уезжает» влево.

Фикс в коде: `center_hvdf_photos_on_canvas` в
`backend/catalog/etl/manual_diagrams.py` — trim S/ST, общий pixel-scale,
центр на 1661×2076, factor по Нм (REF=5).

```bash
poetry run python manage.py attach_manual_diagrams --series hvdf
```

---

## Frontend

| Что | Где |
|-----|-----|
| Plan scale | `frontend/src/utils/productPhotoScale.ts` |
| HV/HVD(+F) baked | `isHvCanvasMediaSku(skuCode)` → `{1, 1}` |
| DA/SA baked | `isDaSaCanvasMediaSku(skuCode)` → `{1, 1}` |
| H81 / H8205 baked | `isKitCanvasMediaSku(skuCode)` → `{1, 1}` |
| Brass DN baked | highlight `dn` → `{1, 1}` |
| Карточка / PDP | `CatalogSkuCard`, `SkuDetailPage` + CSS modules |
| Card WebP (list/mobile) | API `image_card` ≤720px; FE `productCardImageSrc` |

После attach медиа на VPS — догнать превью:

```bash
python manage.py generate_product_image_cards
```

---

## Выкат медиа на VPS

Код (FE/ETL) — git / `deploy-to-vps.sh`.  
Pack-файлы **не в git** — отдельно:

```bash
rsync -az "~/Yandex.Disk.localized/фото для сайта/media-webp/" \
  "hoocon-prod:/var/www/hoocon/media/_pack/media-webp/"
rsync -az "~/Yandex.Disk.localized/фото для сайта/弹簧复位产品/" \
  "hoocon-prod:/var/www/hoocon/media/_pack/hv-sku/"

ssh hoocon-prod 'cd /opt/hoocon && docker compose exec -T web bash -lc "
  python manage.py attach_ball_valve_media_webp --root /app/media/_pack/media-webp
  python manage.py attach_hv_media_webp --root /app/media/_pack/media-webp
  python manage.py attach_hv_sku_media --root /app/media/_pack/hv-sku
  python manage.py attach_hv_catalog_dimensions
  python manage.py attach_da_sa_media_webp --root /app/media/_pack/media-webp
  python manage.py attach_manual_diagrams --series hvdf
  python manage.py generate_product_image_cards
"'
```

Не выкатывать промежуточные pack-итерации на прод, пока локально не «ок».

---

## Чеклист новой семьи

1. Ось размера (DN / Нм / …) и REF.
2. Inventory pack + bak.
3. Normalize → локальный attach → визуальный QA (мелкий vs эталон, поля, центр).
4. FE: baked flag / purpose CSS без double-inset.
5. Тесты на plan / center helper.
6. Финал → rsync + attach на VPS (+ чкд кода при FE/ETL).
