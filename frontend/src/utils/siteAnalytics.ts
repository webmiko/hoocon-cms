/**
 * First-party site analytics (essential cookies — no marketing consent).
 *
 * Posts SPA pageviews to /api/analytics/hit/. Uses Django session for unique
 * visitors. Independent of Yandex Metrika / GA4 (those stay opt-in).
 */

import { api } from "../api/client";

let lastPath: string | null = null;
let csrfReady: Promise<void> | null = null;
let hitTimer: ReturnType<typeof setTimeout> | null = null;

/** Defer hit slightly so LCP is not competing with CSRF + POST. */
export const SITE_ANALYTICS_DELAY_MS = 800;

function ensureCsrf(): Promise<void> {
  if (!csrfReady) {
    csrfReady = api.fetchCsrfToken().then(
      () => undefined,
      () => {
        csrfReady = null;
      },
    );
  }
  return csrfReady;
}

/**
 * Reset dedupe state (tests).
 */
export function resetSiteAnalyticsTracking(): void {
  lastPath = null;
  if (hitTimer !== null) {
    clearTimeout(hitTimer);
    hitTimer = null;
  }
}

/**
 * Classify public SPA path for optional object_type / object_key hints.
 */
export function classifySitePath(path: string): {
  object_type: string;
  object_key: string;
} {
  const normalized = (path.split("?")[0] || "/").replace(/\/+$/, "") || "/";
  if (normalized === "/") {
    return { object_type: "home", object_key: "" };
  }
  const sku = normalized.match(/^\/catalog\/([^/]+)\/([^/]+)$/);
  if (sku) {
    return { object_type: "sku", object_key: sku[2] };
  }
  const catalog = normalized.match(/^\/catalog(?:\/([^/]+))?$/);
  if (catalog) {
    return { object_type: "catalog", object_key: catalog[1] || "" };
  }
  const article = normalized.match(/^\/statyi(?:\/([^/]+))?$/);
  if (article) {
    return { object_type: "article", object_key: article[1] || "" };
  }
  const news = normalized.match(/^\/novosti(?:\/([^/]+))?$/);
  if (news) {
    return { object_type: "news", object_key: news[1] || "" };
  }
  if (normalized === "/search") {
    return { object_type: "search", object_key: "" };
  }
  if (
    normalized === "/rfq" ||
    normalized === "/consultation" ||
    normalized === "/replacement"
  ) {
    return { object_type: "lead", object_key: normalized.slice(1) };
  }
  const page = normalized.match(
    /^\/(company|zavod|faq|kontakty|oferta|privacy-policy|terms|gde-kupit|dokumentaciya)$/,
  );
  if (page) {
    return { object_type: "page", object_key: page[1] };
  }
  return { object_type: "other", object_key: normalized.replace(/^\//, "") };
}

/**
 * Schedule a first-party pageview for the current SPA route.
 *
 * Always runs (essential). Dedupes identical consecutive paths.
 *
 * Args:
 *   path: Canonical path + optional search (search is stripped server-side).
 *   title: Optional document title.
 */
export function trackSitePageView(path: string, title?: string): void {
  const normalized = path || "/";
  if (lastPath === normalized) {
    return;
  }
  lastPath = normalized;

  if (hitTimer !== null) {
    clearTimeout(hitTimer);
  }

  const pageTitle =
    title ?? (typeof document !== "undefined" ? document.title : "");
  const classified = classifySitePath(normalized.split("?")[0] || normalized);

  hitTimer = setTimeout(() => {
    hitTimer = null;
    void (async () => {
      try {
        await ensureCsrf();
        await api.trackSiteHit({
          path: normalized.split("?")[0] || normalized,
          title: pageTitle,
          object_type: classified.object_type,
          object_key: classified.object_key,
        });
      } catch {
        // Best-effort — never break the UI for analytics.
      }
    })();
  }, SITE_ANALYTICS_DELAY_MS);
}
