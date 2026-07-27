import { useEffect, useLayoutEffect } from "react";
import { useLocation, useNavigationType } from "react-router-dom";

import {
  rememberScrollPosition,
  restoreScrollPosition,
  readScrollPosition,
} from "../utils/scrollPositions";

/**
 * Scroll window on route change (SPA navigation).
 *
 * - PUSH/REPLACE → top (or hash target).
 * - POP (back/forward) → restore saved ``location.key`` scroll.
 * - Soft navigations (SKU variant picker) keep scroll.
 *
 * Disables browser ``history.scrollRestoration`` to avoid mobile races
 * that leave the list scrolled to the bottom after catalog → PDP → back.
 */
export function ScrollToTop() {
  const location = useLocation();
  const navigationType = useNavigationType();
  const { pathname, search, hash, state, key } = location;

  useEffect(() => {
    if ("scrollRestoration" in window.history) {
      window.history.scrollRestoration = "manual";
    }
  }, []);

  // Persist scroll for the entry we are leaving.
  useLayoutEffect(() => {
    const entryKey = key;
    return () => {
      rememberScrollPosition(entryKey, window.scrollY);
    };
  }, [key]);

  useEffect(() => {
    const softNav =
      state != null &&
      typeof state === "object" &&
      "softNav" in state &&
      (state as { softNav?: boolean }).softNav === true;
    if (softNav) {
      return;
    }

    if (hash) {
      const id = decodeURIComponent(hash.replace(/^#/, ""));
      const target = id ? document.getElementById(id) : null;
      if (target) {
        target.scrollIntoView({ block: "start" });
        return;
      }
    }

    if (navigationType === "POP") {
      const saved = readScrollPosition(key);
      if (saved !== undefined && saved > 0) {
        return restoreScrollPosition(saved);
      }
      // Unknown history entry — leave as-is (do not force top).
      return;
    }

    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [pathname, search, hash, state, key, navigationType]);

  return null;
}
