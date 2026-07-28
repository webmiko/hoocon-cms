/**
 * Visual product photo scale from rated torque (Нм).
 *
 * Cutout WebPs fill their canvas, so ``object-fit: contain`` makes 5 Нм and
 * 40 Нм look the same size. Linear map keeps the smallest at 75% and the
 * reference max (40 Нм) at 100%. Crops with empty margins are compensated via
 * {@link normalizePhotoScale} using the measured content fill.
 */

/** Reference max for HVAC damper actuators (HVD/HVA 40 Нм = full frame). */
export const PHOTO_SCALE_REF_NM = 40;

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
 * CSS scale factor for a product cutout given rated torque.
 *
 * Linear map: ``refMaxNm`` → 100%, approaching 0 Нм → ``minScale`` (75%).
 *
 * Args:
 *   nm: Rated torque in Нм.
 *   refMaxNm: Torque that fills the media cell (default 40).
 *   minScale: Lower end of the scale (default 0.75).
 *
 * Returns:
 *   Scale in ``[minScale, 1]``.
 */
export function productPhotoScale(
  nm: number,
  {
    refMaxNm = PHOTO_SCALE_REF_NM,
    minScale = PHOTO_SCALE_MIN,
  }: { refMaxNm?: number; minScale?: number } = {},
): number {
  if (!(nm > 0) || !(refMaxNm > 0)) {
    return 1;
  }
  const t = Math.min(nm, refMaxNm) / refMaxNm;
  return minScale + (1 - minScale) * t;
}

/**
 * Resolve torque-only scale from SKU highlights (before crop compensation).
 *
 * Args:
 *   highlights: List/detail highlights.
 *
 * Returns:
 *   Scale 1 when moment is missing (valves, kits, diagrams).
 */
export function photoScaleFromHighlights(
  highlights: ReadonlyArray<{ key: string; value: string }> | null | undefined,
): number {
  const nm = parseMomentNm(momentHighlightValue(highlights));
  if (nm == null) {
    return 1;
  }
  return productPhotoScale(nm);
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
 * Compensate torque scale for empty margins in the photo crop.
 *
 * ``cssScale * contentFill ≈ torqueScale`` so DA5 (tight crop) and DA10 D/DS
 * (lots of padding) land at the same visual size for the same Нм band.
 *
 * Args:
 *   torqueScale: Target visual size from {@link productPhotoScale}.
 *   contentFill: {@link contentFillFromImageData} result.
 *
 * Returns:
 *   CSS ``transform: scale()`` factor, clamped.
 */
export function normalizePhotoScale(
  torqueScale: number,
  contentFill: number,
): number {
  const fill = Math.min(1, Math.max(0.35, contentFill));
  const raw = torqueScale / fill;
  return Math.min(PHOTO_SCALE_CSS_MAX, Math.max(PHOTO_SCALE_CSS_MIN, raw));
}
