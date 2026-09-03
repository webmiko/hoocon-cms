import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  classifySitePath,
  resetSiteAnalyticsTracking,
  SITE_ANALYTICS_DELAY_MS,
  trackSitePageView,
} from "./siteAnalytics";

vi.mock("../api/client", () => ({
  api: {
    fetchCsrfToken: vi.fn(() => Promise.resolve({ csrfToken: "t" })),
    trackSiteHit: vi.fn(() => Promise.resolve({ ok: true })),
  },
}));

import { api } from "../api/client";

describe("siteAnalytics", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    resetSiteAnalyticsTracking();
    vi.mocked(api.fetchCsrfToken).mockClear();
    vi.mocked(api.trackSiteHit).mockClear();
    vi.stubGlobal("document", { title: "Hoocon" });
  });

  afterEach(() => {
    resetSiteAnalyticsTracking();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("classifies catalog SKU paths", () => {
    expect(classifySitePath("/catalog/privody/hva-1")).toEqual({
      object_type: "sku",
      object_key: "hva-1",
    });
  });

  it("posts a hit after delay (essential, no consent gate)", async () => {
    trackSitePageView("/catalog/a/sku-1");
    expect(api.trackSiteHit).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(SITE_ANALYTICS_DELAY_MS);
    await Promise.resolve();

    expect(api.fetchCsrfToken).toHaveBeenCalled();
    expect(api.trackSiteHit).toHaveBeenCalledWith({
      path: "/catalog/a/sku-1",
      title: "Hoocon",
      object_type: "sku",
      object_key: "sku-1",
    });
  });

  it("dedupes identical consecutive paths", async () => {
    trackSitePageView("/company");
    trackSitePageView("/company");
    await vi.advanceTimersByTimeAsync(SITE_ANALYTICS_DELAY_MS);
    await Promise.resolve();
    expect(api.trackSiteHit).toHaveBeenCalledTimes(1);
  });
});
