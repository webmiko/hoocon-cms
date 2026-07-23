/**
 * Sample a horizontal backdrop wash from a product photo.
 *
 * Studio shots use L→R gradients. DA..MU keeps cool grey flat for ~40% then
 * ramps to warm cream — a 2-stop CSS gradient blends too early and looks muddy.
 * We sample several stops along the top edge (product-free) and paint a
 * multi-stop ``linear-gradient(to right, …)``.
 */

export type Rgb = { r: number; g: number; b: number };

export type EdgeWash = {
  left: Rgb;
  right: Rgb;
};

/** One stop in a horizontal wash (``offset`` is 0…1). */
export type WashStop = {
  offset: number;
  color: Rgb;
};

const CORNER_INSET = 2;
const CORNER_SAMPLE = 6;
/** Number of horizontal stops (incl. left and right). */
const WASH_STOP_COUNT = 5;
/** Vertical band height near the top edge for backdrop sampling. */
const TOP_BAND = 8;

/**
 * Average RGB samples into one color.
 *
 * Args:
 *   samples: Non-empty list of channel triples.
 *
 * Returns:
 *   Averaged RGB, or null when samples is empty.
 */
export function averageRgb(samples: readonly Rgb[]): Rgb | null {
  if (samples.length === 0) {
    return null;
  }
  let r = 0;
  let g = 0;
  let b = 0;
  for (const s of samples) {
    r += s.r;
    g += s.g;
    b += s.b;
  }
  const n = samples.length;
  return {
    r: Math.round(r / n),
    g: Math.round(g / n),
    b: Math.round(b / n),
  };
}

/**
 * Format RGB as a CSS ``rgb()`` color.
 */
export function rgbToCss(rgb: Rgb): string {
  return `rgb(${rgb.r}, ${rgb.g}, ${rgb.b})`;
}

/**
 * Channel distance between two colors (L1).
 */
export function rgbDistance(a: Rgb, b: Rgb): number {
  return Math.abs(a.r - b.r) + Math.abs(a.g - b.g) + Math.abs(a.b - b.b);
}

/**
 * Format wash stops as a CSS horizontal multi-stop gradient.
 *
 * Args:
 *   stops: Ordered stops with offsets in 0…1 (at least one).
 *
 * Returns:
 *   ``linear-gradient(to right, …)`` string.
 */
export function washStopsToCss(stops: readonly WashStop[]): string {
  if (stops.length === 0) {
    return "transparent";
  }
  if (stops.length === 1) {
    const only = stops[0];
    if (!only) {
      return "transparent";
    }
    return rgbToCss(only.color);
  }
  const parts = stops.map((s) => {
    const pct = Math.round(s.offset * 100);
    return `${rgbToCss(s.color)} ${pct}%`;
  });
  return `linear-gradient(to right, ${parts.join(", ")})`;
}

/**
 * Format left→right edge wash as a CSS horizontal gradient (2-stop legacy).
 *
 * Args:
 *   wash: Sampled left and right edge colors.
 *
 * Returns:
 *   ``linear-gradient(to right, …)`` string.
 */
export function edgeWashToCss(wash: EdgeWash): string {
  return washStopsToCss([
    { offset: 0, color: wash.left },
    { offset: 1, color: wash.right },
  ]);
}

/**
 * Collect opaque RGB samples from a rectangular block in ImageData.
 */
function collectBlock(
  data: Uint8ClampedArray,
  width: number,
  height: number,
  x0: number,
  y0: number,
  blockW: number,
  blockH: number,
  out: Rgb[],
): void {
  const xStart = Math.max(0, Math.min(width - 1, x0));
  const yStart = Math.max(0, Math.min(height - 1, y0));
  const xEnd = Math.min(width, xStart + blockW);
  const yEnd = Math.min(height, yStart + blockH);
  for (let y = yStart; y < yEnd; y += 1) {
    for (let x = xStart; x < xEnd; x += 1) {
      const i = (y * width + x) * 4;
      const a = data[i + 3] ?? 0;
      // Skip fully transparent pixels (cutouts); wash then falls back to CSS.
      if (a < 16) {
        continue;
      }
      out.push({
        r: data[i] ?? 0,
        g: data[i + 1] ?? 0,
        b: data[i + 2] ?? 0,
      });
    }
  }
}

/**
 * Sample multi-stop horizontal wash along the top edge of ImageData.
 *
 * Top band avoids the product body so mid-frame actuators do not tint stops.
 *
 * Args:
 *   data: Flat RGBA buffer from canvas ``getImageData``.
 *   width: Image width in pixels.
 *   height: Image height in pixels.
 *
 * Returns:
 *   Wash stops, or null if sampling fails.
 */
export function sampleWashStopsFromImageData(
  data: Uint8ClampedArray,
  width: number,
  height: number,
): WashStop[] | null {
  if (width < CORNER_SAMPLE * 2 || height < TOP_BAND + CORNER_INSET) {
    return null;
  }

  const stops: WashStop[] = [];
  const y0 = CORNER_INSET;
  const bandH = Math.min(TOP_BAND, height - y0);
  const last = WASH_STOP_COUNT - 1;

  for (let i = 0; i < WASH_STOP_COUNT; i += 1) {
    const offset = i / last;
    const centerX = Math.round(offset * (width - 1));
    const x0 = Math.max(0, centerX - Math.floor(CORNER_SAMPLE / 2));
    const samples: Rgb[] = [];
    collectBlock(data, width, height, x0, y0, CORNER_SAMPLE, bandH, samples);
    const color = averageRgb(samples);
    if (!color) {
      return null;
    }
    stops.push({ offset, color });
  }

  return stops;
}

/**
 * Drop redundant interior stops; keep plateau ends so flat regions stay flat.
 *
 * DA..MU holds cool grey until ~40% then ramps — collapsing the plateau into a
 * single 0% stop makes CSS blend too early. Same-color runs become
 * ``color 0%, color N%`` then the next distinct stop.
 *
 * Args:
 *   stops: Full sampled stop list.
 *   threshold: Max L1 distance to treat as the same color.
 *
 * Returns:
 *   Compacted stops (always keeps first and last when length ≥ 2).
 */
export function compactWashStops(
  stops: readonly WashStop[],
  threshold: number = 12,
): WashStop[] {
  if (stops.length <= 2) {
    return [...stops];
  }
  const first = stops[0];
  if (!first) {
    return [...stops];
  }
  const out: WashStop[] = [first];
  for (let i = 1; i < stops.length; i += 1) {
    const cur = stops[i];
    const prev = out[out.length - 1];
    if (!prev || !cur) {
      continue;
    }
    if (rgbDistance(prev.color, cur.color) <= threshold) {
      const before = out.length >= 2 ? out[out.length - 2] : null;
      if (before && rgbDistance(before.color, prev.color) <= threshold) {
        // Already have plateau start+end — slide the end forward.
        out[out.length - 1] = { offset: cur.offset, color: prev.color };
      } else {
        // First repeat — record plateau end at this offset.
        out.push({ offset: cur.offset, color: prev.color });
      }
      continue;
    }
    out.push(cur);
  }
  return out;
}

/**
 * Sample left and right edge colors from ImageData (RGBA).
 *
 * Left/right from multi-stop top-edge wash (first and last stops).
 *
 * Args:
 *   data: Flat RGBA buffer from canvas ``getImageData``.
 *   width: Image width in pixels.
 *   height: Image height in pixels.
 *
 * Returns:
 *   Edge wash, or null if sampling fails.
 */
export function sampleEdgeWashFromImageData(
  data: Uint8ClampedArray,
  width: number,
  height: number,
): EdgeWash | null {
  const stops = sampleWashStopsFromImageData(data, width, height);
  if (!stops || stops.length < 2) {
    return null;
  }
  const left = stops[0]?.color;
  const right = stops[stops.length - 1]?.color;
  if (!left || !right) {
    return null;
  }
  return { left, right };
}

/**
 * Average of edge wash ends (legacy solid wash).
 *
 * Args:
 *   data: Flat RGBA buffer from canvas ``getImageData``.
 *   width: Image width in pixels.
 *   height: Image height in pixels.
 *
 * Returns:
 *   Averaged edge color, or null if dimensions are unusable.
 */
export function sampleEdgeColorFromImageData(
  data: Uint8ClampedArray,
  width: number,
  height: number,
): Rgb | null {
  const wash = sampleEdgeWashFromImageData(data, width, height);
  if (!wash) {
    return null;
  }
  return averageRgb([wash.left, wash.right]);
}

/**
 * Draw ``img`` to a canvas and return CSS wash + accent matching the backdrop.
 *
 * Args:
 *   img: Decoded HTMLImageElement (same-origin or CORS-enabled).
 *
 * Returns:
 *   ``{ css, accent }`` or null on failure. ``accent`` is a darkened average of
 *   wash stops for borders/chrome that still read on light surfaces.
 */
export function sampleEdgeMatchFromImage(
  img: HTMLImageElement,
): { css: string; accent: string } | null {
  const width = img.naturalWidth || img.width;
  const height = img.naturalHeight || img.height;
  if (!width || !height) {
    return null;
  }

  const canvas = document.createElement("canvas");
  // Cap work for large product shots; color is still representative.
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
    const stops = sampleWashStopsFromImageData(data, w, h);
    if (!stops) {
      return null;
    }
    const compact = compactWashStops(stops);
    return {
      css: washStopsToCss(compact),
      accent: accentCssFromWashStops(compact),
    };
  } catch {
    // SecurityError when canvas is tainted.
    return null;
  }
}

/**
 * Solid accent from wash stops (darkened average for hover borders).
 */
export function accentCssFromWashStops(stops: readonly WashStop[]): string {
  const avg = averageRgb(stops.map((s) => s.color));
  if (!avg) {
    return "transparent";
  }
  // Studio washes are pale; darken so the card border stays visible.
  const k = 0.7;
  return `rgb(${Math.round(avg.r * k)}, ${Math.round(avg.g * k)}, ${Math.round(avg.b * k)})`;
}

/**
 * Draw ``img`` to a canvas and return CSS horizontal wash matching the backdrop.
 *
 * Args:
 *   img: Decoded HTMLImageElement (same-origin or CORS-enabled).
 *
 * Returns:
 *   Multi-stop ``linear-gradient(to right, …)`` or null on failure.
 */
export function sampleEdgeCssFromImage(img: HTMLImageElement): string | null {
  return sampleEdgeMatchFromImage(img)?.css ?? null;
}
