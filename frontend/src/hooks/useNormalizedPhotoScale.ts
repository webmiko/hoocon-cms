import { useEffect, useState } from "react";

import {
  measureContentFillFromImage,
  normalizePhotoScale,
  PHOTO_SCALE_CSS_MAX,
} from "../utils/productPhotoScale";

const fillBySrc = new Map<string, number>();

/**
 * Torque/DN photo scale compensated for empty crop margins.
 *
 * Until the image is measured, returns ``torqueScale`` alone (clamped to
 * ``maxCssScale``). Session-cached fills avoid re-decode flash on remount.
 *
 * Args:
 *   src: Product ``/media/...`` URL (same-origin).
 *   torqueScale: From ``photoScalePlanFromHighlights().target``.
 *   maxCssScale: From ``photoScalePlanFromHighlights().maxCssScale``.
 *
 * Returns:
 *   CSS scale for ``--photo-scale``.
 */
export function useNormalizedPhotoScale(
  src: string | null | undefined,
  torqueScale: number,
  maxCssScale: number = PHOTO_SCALE_CSS_MAX,
): number {
  const [asyncFill, setAsyncFill] = useState<{
    src: string;
    fill: number;
  } | null>(null);

  useEffect(() => {
    if (!src) {
      return;
    }
    if (fillBySrc.has(src)) {
      return;
    }

    let cancelled = false;
    const img = new Image();
    img.decoding = "async";
    img.onload = () => {
      if (cancelled) {
        return;
      }
      const measured = measureContentFillFromImage(img);
      if (measured == null) {
        return;
      }
      fillBySrc.set(src, measured);
      setAsyncFill({ src, fill: measured });
    };
    img.src = src;

    return () => {
      cancelled = true;
      img.onload = null;
    };
  }, [src]);

  const pending = Math.min(maxCssScale, torqueScale);

  if (!src) {
    return pending;
  }
  const cached = fillBySrc.get(src);
  if (cached != null) {
    return normalizePhotoScale(torqueScale, cached, maxCssScale);
  }
  if (asyncFill?.src === src) {
    return normalizePhotoScale(torqueScale, asyncFill.fill, maxCssScale);
  }
  return pending;
}
