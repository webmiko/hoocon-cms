import { useEffect, useState } from "react";

import {
  locationHashMatches,
  scrollGateSatisfied,
} from "./deferredMountGates";
import { useNearViewport } from "./useNearViewport";

type UseDeferredMountOptions = {
  rootMargin?: string;
  /** Mount only after the user scrolls at least this many pixels. */
  requireScrollPx?: number;
  /** Mount when ``location.hash`` matches (without ``#``). */
  hashIds?: readonly string[];
};

function hashMatches(ids: readonly string[] | undefined): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return locationHashMatches(ids, window.location.hash);
}

/**
 * Near-viewport gate plus optional scroll / hash triggers.
 *
 * Use on home quiz so PSI (no scroll) does not download heavy chunks on first paint.
 */
export function useDeferredMount(options: UseDeferredMountOptions = {}) {
  const { rootMargin, requireScrollPx, hashIds } = options;
  const { ref, ready: near } = useNearViewport({ rootMargin });
  const [scrolled, setScrolled] = useState(() =>
    requireScrollPx === undefined
      ? true
      : typeof window !== "undefined" && window.scrollY >= requireScrollPx,
  );
  const [hashHit, setHashHit] = useState(() => hashMatches(hashIds));

  useEffect(() => {
    if (requireScrollPx === undefined) {
      return;
    }
    const onScroll = () => {
      if (window.scrollY >= requireScrollPx) {
        setScrolled(true);
      }
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [requireScrollPx]);

  useEffect(() => {
    if (!hashIds?.length) {
      return;
    }
    const onHash = () => setHashHit(hashMatches(hashIds));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [hashIds]);

  const scrollGate = scrollGateSatisfied(requireScrollPx, scrolled, hashHit);
  const ready = near && scrollGate;

  return { ref, ready };
}
