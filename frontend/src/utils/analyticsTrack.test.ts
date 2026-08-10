import { afterEach, describe, expect, it, vi } from "vitest";

import {
  LEAD_SUBMIT_GOAL,
  resetSpaHitTracking,
  setAnalyticsCounters,
  trackLeadSubmit,
  trackSpaHit,
} from "./analyticsTrack";

describe("analyticsTrack", () => {
  afterEach(() => {
    resetSpaHitTracking();
    setAnalyticsCounters("", "");
    delete window.ym;
    delete window.gtag;
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
});
