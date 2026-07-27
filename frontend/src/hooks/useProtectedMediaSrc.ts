import { useEffect, useState } from "react";

import {
  peekProtectedMediaSrc,
  resolveProtectedMediaSrc,
} from "../utils/protectedMediaSrc";

/**
 * Load ``src`` as a session-cached ``blob:`` URL for product images.
 *
 * Falls back to the original ``src`` if fetch fails (image still shows).
 * Returns ``null`` while the first resolution is in flight or ``src`` is empty.
 * Session cache is read synchronously so remounts (SPA navigation) do not
 * flash a transparent placeholder when the blob is already known.
 */
export function useProtectedMediaSrc(
  src: string | null | undefined,
): string | null {
  const [asyncUrl, setAsyncUrl] = useState<{
    src: string;
    url: string;
  } | null>(null);

  useEffect(() => {
    if (!src) {
      return;
    }
    if (peekProtectedMediaSrc(src)) {
      return;
    }

    let cancelled = false;
    void resolveProtectedMediaSrc(src)
      .then((url) => {
        if (!cancelled) {
          setAsyncUrl({ src, url });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAsyncUrl({ src, url: src });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [src]);

  if (!src) {
    return null;
  }
  const cached = peekProtectedMediaSrc(src);
  if (cached) {
    return cached;
  }
  if (asyncUrl?.src === src) {
    return asyncUrl.url;
  }
  return null;
}
