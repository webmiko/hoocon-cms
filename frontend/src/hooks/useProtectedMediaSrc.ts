import { useEffect, useState } from "react";

import { resolveProtectedMediaSrc } from "../utils/protectedMediaSrc";

/**
 * Load ``src`` as a session-cached ``blob:`` URL for product images.
 *
 * Falls back to the original ``src`` if fetch fails (image still shows).
 * Returns ``null`` while the first resolution is in flight or ``src`` is empty.
 */
export function useProtectedMediaSrc(
  src: string | null | undefined,
): string | null {
  const [resolved, setResolved] = useState<{
    src: string;
    url: string;
  } | null>(null);

  useEffect(() => {
    if (!src) {
      return;
    }

    let cancelled = false;
    void resolveProtectedMediaSrc(src)
      .then((url) => {
        if (!cancelled) {
          setResolved({ src, url });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setResolved({ src, url: src });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [src]);

  if (!src) {
    return null;
  }
  if (resolved?.src === src) {
    return resolved.url;
  }
  return null;
}
