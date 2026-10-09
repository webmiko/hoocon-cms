import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  applyAnalyticsConsent,
  LEAD_SUBMIT_GOAL,
  QUIZ_COMPLETE_GOAL,
  QUIZ_START_GOAL,
  QUIZ_TO_CATALOG_GOAL,
  resetSpaHitTracking,
  setAnalyticsCounters,
  trackLeadSubmit,
  trackQuizComplete,
  trackQuizStart,
  trackQuizToCatalog,
  trackSpaHit,
} from "./analyticsTrack";
import { buildCookieConsent, COOKIE_CONSENT_STORAGE_KEY } from "./cookieConsent";

describe("analyticsTrack", () => {
  beforeEach(() => {
    localStorage.setItem(COOKIE_CONSENT_STORAGE_KEY, JSON.stringify(buildCookieConsent(true)));
    vi.stubGlobal("window", {} as Window & typeof globalThis);
    vi.stubGlobal("document", { title: "Hoocon test" });
  });

  afterEach(() => {
    resetSpaHitTracking();
    setAnalyticsCounters("", "");
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("stops Metrika/GA4 goals and hits right after consent is withdrawn", () => {
    const ym = vi.fn();
    const gtag = vi.fn();
    window.ym = ym;
    window.gtag = gtag;
    setAnalyticsCounters("7", "G-OFF");
    trackSpaHit("/");

    localStorage.setItem(COOKIE_CONSENT_STORAGE_KEY, JSON.stringify(buildCookieConsent(false)));
    trackSpaHit("/catalog");
    trackLeadSubmit("rfq");
    trackQuizStart();
    expect(ym).not.toHaveBeenCalled();
    expect(gtag).not.toHaveBeenCalled();
  });

  it("toggles the GA4 kill switch with consent", () => {
    const gtag = vi.fn();
    window.gtag = gtag;
    setAnalyticsCounters("", "G-SW");
    const flags = window as unknown as Record<string, unknown>;

    applyAnalyticsConsent(false);
    expect(flags["ga-disable-G-SW"]).toBe(true);
    expect(gtag).toHaveBeenCalledWith("consent", "update", { analytics_storage: "denied" });

    applyAnalyticsConsent(true);
    expect(flags["ga-disable-G-SW"]).toBe(false);
  });

  it("skips the first SPA hit, then sends Metrika hit and GA4 page_view", () => {
    const ym = vi.fn();
    const gtag = vi.fn();
    window.ym = ym;
    window.gtag = gtag;
    setAnalyticsCounters("123456", "G-TEST");

    trackSpaHit("/");
    expect(ym).not.toHaveBeenCalled();
    expect(gtag).not.toHaveBeenCalled();

    trackSpaHit("/catalog");
    expect(ym).toHaveBeenCalledWith(123456, "hit", "/catalog", {
      title: expect.any(String),
    });
    expect(gtag).toHaveBeenCalledWith("event", "page_view", {
      page_path: "/catalog",
      page_title: expect.any(String),
      send_to: "G-TEST",
    });

    trackSpaHit("/catalog");
    expect(ym).toHaveBeenCalledTimes(1);
  });

  it("fires lead_submit goal and generate_lead without PII", () => {
    const ym = vi.fn();
    const gtag = vi.fn();
    window.ym = ym;
    window.gtag = gtag;
    setAnalyticsCounters("99", "G-LEAD");

    trackLeadSubmit("rfq");
    expect(ym).toHaveBeenCalledWith(99, "reachGoal", LEAD_SUBMIT_GOAL, {
      lead_type: "rfq",
    });
    expect(gtag).toHaveBeenCalledWith("event", "generate_lead", {
      lead_type: "rfq",
      send_to: "G-LEAD",
    });
  });

  it("no-ops when counters are unset", () => {
    const ym = vi.fn();
    window.ym = ym;
    trackSpaHit("/");
    trackSpaHit("/x");
    trackLeadSubmit("consultation");
    expect(ym).not.toHaveBeenCalled();
  });

  it("fires quiz goals in Metrika", () => {
    const ym = vi.fn();
    window.ym = ym;
    setAnalyticsCounters("42", "");

    trackQuizStart();
    trackQuizComplete({ category: "sharovye-krany", count: 3, relaxed: false });
    trackQuizToCatalog();

    expect(ym).toHaveBeenCalledWith(42, "reachGoal", QUIZ_START_GOAL, undefined);
    expect(ym).toHaveBeenCalledWith(42, "reachGoal", QUIZ_COMPLETE_GOAL, {
      category: "sharovye-krany",
      count: 3,
      relaxed: false,
    });
    expect(ym).toHaveBeenCalledWith(42, "reachGoal", QUIZ_TO_CATALOG_GOAL, undefined);
  });
});
