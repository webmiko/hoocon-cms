import { describe, expect, it } from "vitest";

import {
  buildCookieConsent,
  isAnalyticsAllowed,
  isMarketingAllowed,
  parseCookieConsent,
} from "./cookieConsent";

describe("parseCookieConsent", () => {
  it("returns null for empty storage", () => {
    expect(parseCookieConsent(null)).toBeNull();
    expect(parseCookieConsent("")).toBeNull();
  });

  it("migrates legacy accepted / declined", () => {
    expect(parseCookieConsent("accepted")?.analytics).toBe(true);
    expect(parseCookieConsent("declined")?.analytics).toBe(false);
    expect(parseCookieConsent("accepted")?.essential).toBe(true);
    expect(parseCookieConsent("accepted")?.marketing).toBe(false);
  });

  it("parses granular JSON", () => {
    const raw = JSON.stringify(buildCookieConsent(true, true));
    const parsed = parseCookieConsent(raw);
    expect(parsed?.analytics).toBe(true);
    expect(parsed?.marketing).toBe(true);
    expect(parsed?.essential).toBe(true);
    expect(parsed?.version).toBe(2);
  });

  it("defaults marketing false for v1 JSON", () => {
    const raw = JSON.stringify({
      version: 1,
      essential: true,
      analytics: true,
      updatedAt: new Date().toISOString(),
    });
    expect(parseCookieConsent(raw)?.marketing).toBe(false);
  });

  it("rejects invalid JSON shapes", () => {
    expect(parseCookieConsent("{}")).toBeNull();
    expect(parseCookieConsent('{"analytics":"yes"}')).toBeNull();
    expect(parseCookieConsent("not-json")).toBeNull();
  });
});

describe("isAnalyticsAllowed", () => {
  it("requires explicit analytics opt-in", () => {
    expect(isAnalyticsAllowed(null)).toBe(false);
    expect(isAnalyticsAllowed(buildCookieConsent(false))).toBe(false);
    expect(isAnalyticsAllowed(buildCookieConsent(true))).toBe(true);
  });
});

describe("isMarketingAllowed", () => {
  it("requires explicit marketing opt-in", () => {
    expect(isMarketingAllowed(null)).toBe(false);
    expect(isMarketingAllowed(buildCookieConsent(true, false))).toBe(false);
    expect(isMarketingAllowed(buildCookieConsent(true, true))).toBe(true);
  });
});
