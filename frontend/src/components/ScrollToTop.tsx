import { useEffect } from "react";
import { useLocation } from "react-router-dom";

/**
 * Scroll window to top on route change (SPA navigation).
 * Hash links scroll to the matching element when present.
 * Soft navigations (SKU variant picker) keep scroll position.
 */
export function ScrollToTop() {
  const location = useLocation();
  const { pathname, search, hash, state } = location;

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
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [pathname, search, hash, state]);

  return null;
}
