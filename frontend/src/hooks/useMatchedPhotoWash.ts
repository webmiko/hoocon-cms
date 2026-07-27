import { useEffect, useState } from "react";

import { sampleEdgeMatchFromImage } from "../utils/sampleImageEdgeColor";

export type MatchedPhotoWash = {
  /** Multi-stop L→R gradient CSS for the media backdrop. */
  css: string;
  /** Solid accent from the wash (hover borders, chrome). */
  accent: string;
};

const washBySrc = new Map<string, MatchedPhotoWash>();

/**
 * Resolve a CSS background wash that matches the photo's edge backdrop.
 *
 * Samples several top-edge stops into a multi-stop L→R gradient so non-linear
 * studio backdrops (DA..MU: flat grey then cream ramp) stay smooth.
 *
 * Args:
 *   src: Image URL (prefer root-relative ``/media/...`` for same-origin canvas).
 *
 * Returns:
 *   Sampled wash + accent, or undefined while loading / on failure.
 *   Session-cached washes return synchronously on remount (no backdrop flash).
 */
export function useMatchedPhotoWash(
  src: string | null | undefined,
): MatchedPhotoWash | undefined {
  const [asyncMatch, setAsyncMatch] = useState<{
    src: string;
    match: MatchedPhotoWash;
  } | null>(null);

  useEffect(() => {
    if (!src) {
      return;
    }
    if (washBySrc.get(src)) {
      return;
    }

    let cancelled = false;
    const img = new Image();
    // Same-origin /media via Vite proxy; keeps canvas readable.
    img.decoding = "async";
    img.onload = () => {
      if (cancelled) {
        return;
      }
      const match = sampleEdgeMatchFromImage(img);
      if (match) {
        washBySrc.set(src, match);
        setAsyncMatch({ src, match });
      }
    };
    img.onerror = () => {
      // Leave undefined; caller keeps purpose-token wash.
    };
    img.src = src;

    return () => {
      cancelled = true;
      img.onload = null;
      img.onerror = null;
    };
  }, [src]);

  if (!src) {
    return undefined;
  }
  const cached = washBySrc.get(src);
  if (cached) {
    return cached;
  }
  if (asyncMatch?.src === src) {
    return asyncMatch.match;
  }
  return undefined;
}
