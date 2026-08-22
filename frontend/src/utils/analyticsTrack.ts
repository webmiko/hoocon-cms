/**
 * Analytics events after consent (Yandex Metrika + GA4).
 *
 * Counter scripts load in Analytics.tsx; this module only fires when APIs exist.
 */

export type LeadTrackType = "rfq" | "consultation" | "replacement";

/** YM goal name — create the same goal in Metrika UI. */
export const LEAD_SUBMIT_GOAL = "lead_submit";

export const QUIZ_START_GOAL = "quiz_start";
export const QUIZ_COMPLETE_GOAL = "quiz_complete";
export const QUIZ_TO_CATALOG_GOAL = "quiz_to_catalog";
export const QUIZ_TO_CONSULTATION_GOAL = "quiz_to_consultation";

let lastSpaHitPath: string | null = null;
let ymCounterId: number | null = null;
let ga4Id: string | null = null;

/**
 * Remember loaded counter IDs so hits/goals can fire without re-fetch.
 *
 * Args:
 *   yandexId: Numeric Metrika counter id string, or empty.
 *   ga4MeasurementId: GA4 measurement id (G-…), or empty.
 */
export function setAnalyticsCounters(
  yandexId: string,
  ga4MeasurementId: string,
): void {
  const ym = Number(yandexId);
  ymCounterId = Number.isFinite(ym) && ym > 0 ? ym : null;
  ga4Id =
    ga4MeasurementId.startsWith("G-") ? ga4MeasurementId : null;
}

/** Reset SPA hit dedupe (tests / consent re-init). */
export function resetSpaHitTracking(): void {
  lastSpaHitPath = null;
}

/**
 * SPA pageview after client navigation.
 *
 * Skips the first call per session so Metrika/GA4 init is not double-counted.
 * Subsequent route changes send ``hit`` / ``page_view``.
 *
 * Args:
 *   path: Canonical path + search (e.g. ``/catalog?new=1``).
 *   title: Optional document title override.
 */
export function trackSpaHit(path: string, title?: string): void {
  const normalized = path || "/";
  if (lastSpaHitPath === null) {
    lastSpaHitPath = normalized;
    return;
  }
  if (lastSpaHitPath === normalized) {
    return;
  }
  lastSpaHitPath = normalized;

  const pageTitle = title ?? (typeof document !== "undefined" ? document.title : "");
  if (ymCounterId !== null && typeof window !== "undefined" && window.ym) {
    window.ym(ymCounterId, "hit", normalized, { title: pageTitle });
  }
  if (ga4Id !== null && typeof window !== "undefined" && window.gtag) {
    window.gtag("event", "page_view", {
      page_path: normalized,
      page_title: pageTitle,
      send_to: ga4Id,
    });
  }
}

/**
 * Conversion goal after a successful lead create.
 *
 * Args:
 *   leadType: RFQ / consultation / Belimo replacement.
 */
export function trackLeadSubmit(leadType: LeadTrackType): void {
  if (ymCounterId !== null && typeof window !== "undefined" && window.ym) {
    window.ym(ymCounterId, "reachGoal", LEAD_SUBMIT_GOAL, {
      lead_type: leadType,
    });
  }
  if (typeof window !== "undefined" && window.gtag) {
    window.gtag("event", "generate_lead", {
      lead_type: leadType,
      ...(ga4Id ? { send_to: ga4Id } : {}),
    });
  }
}

function trackQuizGoal(
  goal: string,
  params?: Record<string, string | number | boolean>,
): void {
  if (ymCounterId !== null && typeof window !== "undefined" && window.ym) {
    window.ym(ymCounterId, "reachGoal", goal, params);
  }
  if (typeof window !== "undefined" && window.gtag) {
    window.gtag("event", goal, {
      ...(params ?? {}),
      ...(ga4Id ? { send_to: ga4Id } : {}),
    });
  }
}

/** First answer beyond the opening step. */
export function trackQuizStart(): void {
  trackQuizGoal(QUIZ_START_GOAL);
}

/** Quiz finished and preview loaded (or empty). */
export function trackQuizComplete(params: {
  category: string;
  count: number;
  relaxed: boolean;
}): void {
  trackQuizGoal(QUIZ_COMPLETE_GOAL, params);
}

/** User opens the filtered catalog from quiz results. */
export function trackQuizToCatalog(): void {
  trackQuizGoal(QUIZ_TO_CATALOG_GOAL);
}

/** User opens consultation from quiz results. */
export function trackQuizToConsultation(): void {
  trackQuizGoal(QUIZ_TO_CONSULTATION_GOAL);
}
