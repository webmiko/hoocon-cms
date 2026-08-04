import { useEffect, useRef, useState, type RefObject } from "react";

type UseNearViewportOptions = {
  /** CSS margin around the root (default: start ~240px before visible). */
  rootMargin?: string;
  /** When true (default), stay ready after the first intersection. */
  once?: boolean;
};

/**
 * Become ready when ``ref`` nears the viewport (IntersectionObserver).
 *
 * Falls back to ready immediately when IO is missing (old engines / tests).
 */
export function useNearViewport(
  options: UseNearViewportOptions = {},
): {
  ref: RefObject<HTMLDivElement | null>;
  ready: boolean;
} {
  const { rootMargin = "240px 0px", once = true } = options;
  const ref = useRef<HTMLDivElement | null>(null);
  const [ready, setReady] = useState(
    () => typeof IntersectionObserver === "undefined",
  );

  useEffect(() => {
    if (ready && once) {
      return;
    }
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const hit = entries.some((entry) => entry.isIntersecting);
        if (!hit) {
          return;
        }
        setReady(true);
        if (once) {
          observer.disconnect();
        }
      },
      { root: null, rootMargin, threshold: 0 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [ready, once, rootMargin]);

  return { ref, ready };
}
