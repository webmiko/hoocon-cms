/**
 * Visual product photo scale from rated torque (Нм) or valve DN.
 *
 * Cutout WebPs fill their canvas, so ``object-fit: contain`` makes 5 Нм and
 * 40 Нм look the same size. Linear map keeps the smallest at 75% and the
 * reference max (40 Нм / DN 50) at 100%. Crops with empty margins are
 * compensated via {@link normalizePhotoScale} using the measured content fill.
 *
 * Ball-valve heroes have no moment — without a DN map, ``torqueScale=1`` plus
 * fill compensation pushes DN20+ past the cell and clips the cutout.
 */

/** Reference max for HVAC damper actuators (HVD/HVA 40 Нм = full frame). */
export const PHOTO_SCALE_REF_NM = 40;

/** Reference max DN for brass / flanged valve bodies (DN50 = full frame). */
export const PHOTO_SCALE_REF_DN = 50;

/** Smallest actuators still read clearly in the card media cell. */
export const PHOTO_SCALE_MIN = 0.75;

/** Lower clamp after crop compensation (sparse D/DS packs). */
export const PHOTO_SCALE_CSS_MIN = 0.65;

/** Upper clamp after crop compensation (avoid overflowing the media cell). */
export const PHOTO_SCALE_CSS_MAX = 1.5;

/**
 * Parse rated torque in Нм from a highlight / attribute value.
 *
 * Args:
 *   value: e.g. ``5 Нм``, ``40``, ``5.0 Nm``.
 *
 * Returns:
 *   Positive Nm, or null when not parseable.
 */
export function parseMomentNm(value: string | null | undefined): number | null {
  if (!value) {
    return null;
  }
  const trimmed = value.trim();
  // Bare number (API sometimes omits the unit on moment rows).
  if (/^\d+(?:[.,]\d+)?$/.test(trimmed)) {
    const bare = Number.parseFloat(trimmed.replace(",", "."));
    return Number.isFinite(bare) && bare > 0 ? bare : null;
  }
  // Require Нм/nm so voltage strings like «AC/DC 24 В» are ignored.
  // Avoid ``\b`` after Cyrillic — JS word boundaries are ASCII-oriented.
  const match = trimmed.match(/(\d+(?:[.,]\d+)?)\s*(?:нм|nm)(?=$|[\s,;.])/i);
  if (!match) {
    return null;
  }
  const nm = Number.parseFloat(match[1].replace(",", "."));
  if (!Number.isFinite(nm) || nm <= 0) {
    return null;
  }
  return nm;
}

/**
 * Moment highlight value from a SKU highlights list.
 *
 * Args:
 *   highlights: Catalog highlight rows (may be undefined).
 *
 * Returns:
 *   Moment value string, or undefined.
 */
export function momentHighlightValue(
  highlights: ReadonlyArray<{ key: string; value: string }> | null | undefined,
): string | undefined {
  if (!highlights?.length) {
    return undefined;
  }
  return highlights.find((h) => h.key === "moment")?.value;
}

/**
 * DN highlight value from a SKU highlights list.
 *
 * Args:
 *   highlights: Catalog highlight rows (may be undefined).
 *
 * Returns:
 *   DN value string, or undefined.
 */
export function dnHighlightValue(
  highlights: ReadonlyArray<{ key: string; value: string }> | null | undefined,
): string | undefined {
  if (!highlights?.length) {
    return undefined;
  }
  return highlights.find((h) => h.key === "dn")?.value;
}

/**
 * Parse nominal diameter from a highlight / attribute value.
 *
 * Args:
 *   value: e.g. ``20``, ``DN20``, ``DN 50``.
 *
 * Returns:
 *   Positive DN, or null when not parseable.
 */
export function parseDn(value: string | null | undefined): number | null {
  if (!value) {
    return null;
  }
  const match = value.trim().match(/^(?:dn\s*)?(\d+(?:[.,]\d+)?)$/i);
  if (!match) {
    return null;
  }
  const dn = Number.parseFloat(match[1].replace(",", "."));
  if (!Number.isFinite(dn) || dn <= 0) {
    return null;
  }
  return dn;
}

/**
 * CSS scale factor for a product cutout given rated torque or DN.
 *
 * Linear map: ``refMax`` → 100%, approaching 0 → ``minScale`` (75%).
 *
 * Args:
 *   value: Rated torque in Нм, or DN.
 *   refMax: Value that fills the media cell (default 40 Нм).
 *   minScale: Lower end of the scale (default 0.75).
 *
 * Returns:
 *   Scale in ``[minScale, 1]``.
 */
export function productPhotoScale(
  value: number,
  {
    refMaxNm = PHOTO_SCALE_REF_NM,
    minScale = PHOTO_SCALE_MIN,
  }: { refMaxNm?: number; minScale?: number } = {},
): number {
  if (!(value > 0) || !(refMaxNm > 0)) {
    return 1;
  }
  const t = Math.min(value, refMaxNm) / refMaxNm;
  return minScale + (1 - minScale) * t;
}

/** Target visual size + CSS clamp after fill compensation. */
export type PhotoScalePlan = {
  target: number;
  /**
   * Sparse DA/SA crops may exceed 1. Baked HV / valve packs must stay ≤1 —
   * denser heroes already fill the cell and clip when boosted.
   */
  maxCssScale: number;
};

/**
 * HVA/HVD air SKUs whose heroes are sized on the shared media-webp canvas.
 *
 * Smoke ``…F`` editions are excluded (no Nm canvas pack yet).
 */
export function isHvCanvasMediaSku(skuCode: string | null | undefined): boolean {
  // Air HVA/HVD (+Q/QX/P) and smoke HVD-…F — relative size baked into heroes.
  return /^(?:hva|hvd)(?:24|230)s?t?-\d+(?:f|qx|q|p)?$/i.test((skuCode || "").trim());
}

/**
 * Resolve torque or DN scale plan from SKU highlights (before crop compensation).
 *
 * Baked packs (brass DN, HVA/HVD Nm) keep ``target`` / ``maxCssScale`` at 1 so
 * CSS does not apply a second relative shrink. Other actuators (DA/SA, HVDF)
 * still map moment → 75…100% with fill boost up to ``PHOTO_SCALE_CSS_MAX``.
 *
 * Args:
 *   highlights: List/detail highlights.
 *   skuCode: Optional SKU code to detect baked HV air heroes.
 *
 * Returns:
 *   Target / maxCss plan.
 */
export function photoScalePlanFromHighlights(
  highlights: ReadonlyArray<{ key: string; value: string }> | null | undefined,
  skuCode?: string | null,
): PhotoScalePlan {
  // HVA/HVD air: Nm hierarchy is baked into media-webp (do not FE-scale again).
  if (isHvCanvasMediaSku(skuCode)) {
    return { target: 1, maxCssScale: 1 };
  }
  const nm = parseMomentNm(momentHighlightValue(highlights));
  if (nm != null) {
    return {
      target: productPhotoScale(nm),
      maxCssScale: PHOTO_SCALE_CSS_MAX,
    };
  }
  // Brass / DN bodies: relative size is baked into shared cutouts.
  if (parseDn(dnHighlightValue(highlights)) != null) {
    return { target: 1, maxCssScale: 1 };
  }
  return { target: 1, maxCssScale: PHOTO_SCALE_CSS_MAX };
}

/**
 * Target visual scale from highlights (before crop compensation).
 *
 * Prefer {@link photoScalePlanFromHighlights} when the CSS clamp matters.
 */
export function photoScaleFromHighlights(
  highlights: ReadonlyArray<{ key: string; value: string }> | null | undefined,
  skuCode?: string | null,
): number {
  return photoScalePlanFromHighlights(highlights, skuCode).target;
}

/**
 * Geometric-mean content fill of a product cutout (0…1).
 *
 * Ignores transparent and near-white pixels so studio margins do not count.
 *
 * Args:
 *   data: RGBA ``ImageData.data``.
 *   width: Bitmap width.
 *   height: Bitmap height.
 *
 * Returns:
 *   ``sqrt(fillW * fillH)``, or 1 when no content / full bleed.
 */
export function contentFillFromImageData(
  data: Uint8ClampedArray,
  width: number,
  height: number,
): number {
  if (width < 1 || height < 1 || data.length < width * height * 4) {
    return 1;
  }
  let minX = width;
  let minY = height;
  let maxX = -1;
  let maxY = -1;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const i = (y * width + x) * 4;
      const alpha = data[i + 3];
      if (alpha < 24) {
        continue;
      }
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      // Near-white / washed studio backdrop.
      if (r > 248 && g > 248 && b > 248) {
        continue;
      }
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x > maxX) maxX = x;
      if (y > maxY) maxY = y;
    }
  }
  if (maxX < 0) {
    return 1;
  }
  const fillW = (maxX - minX + 1) / width;
  const fillH = (maxY - minY + 1) / height;
  return Math.sqrt(Math.max(0.01, fillW * fillH));
}

/**
 * Draw ``img`` and return geometric-mean content fill (0…1).
 *
 * Args:
 *   img: Decoded same-origin product photo.
 *
 * Returns:
 *   Fill ratio, or null when canvas read fails.
 */
export function measureContentFillFromImage(img: HTMLImageElement): number | null {
  const width = img.naturalWidth || img.width;
  const height = img.naturalHeight || img.height;
  if (!width || !height) {
    return null;
  }
  const canvas = document.createElement("canvas");
  const maxEdge = 160;
  const scale = Math.min(1, maxEdge / Math.max(width, height));
  const w = Math.max(1, Math.round(width * scale));
  const h = Math.max(1, Math.round(height * scale));
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) {
    return null;
  }
  try {
    ctx.drawImage(img, 0, 0, w, h);
    const { data } = ctx.getImageData(0, 0, w, h);
    return contentFillFromImageData(data, w, h);
  } catch {
    return null;
  }
}

/**
 * Compensate torque/DN scale for empty margins in the photo crop.
 *
 * ``cssScale * contentFill ≈ target`` so DA5 (tight crop) and DA10 D/DS
 * (lots of padding) land at the same visual size for the same Нм band.
 *
 * Valve DN heroes cap at ``maxCssScale=1``; side air comes from CSS padding on
 * the media block, not from shrinking the WebP or ``margin`` on the ``img``.
 *
 * Args:
 *   torqueScale: Target visual size from {@link productPhotoScale}.
 *   contentFill: {@link contentFillFromImageData} result.
 *   maxCssScale: Upper clamp (1 for valve DN; ``PHOTO_SCALE_CSS_MAX`` for Нм).
 *
 * Returns:
 *   CSS ``transform: scale()`` factor, clamped.
 */
export function normalizePhotoScale(
  torqueScale: number,
  contentFill: number,
  maxCssScale: number = PHOTO_SCALE_CSS_MAX,
): number {
  const fill = Math.min(1, Math.max(0.35, contentFill));
  const raw = torqueScale / fill;
  const upper = Math.min(PHOTO_SCALE_CSS_MAX, Math.max(PHOTO_SCALE_CSS_MIN, maxCssScale));
  return Math.min(upper, Math.max(PHOTO_SCALE_CSS_MIN, raw));
}
