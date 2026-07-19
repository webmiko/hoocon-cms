import { describe, expect, it } from "vitest";

import {
  nextThemePreference,
  parseThemePreference,
  resolveTheme,
  themePreferenceLabel,
} from "./theme";

describe("parseThemePreference", () => {
  it("accepts light, dark, system", () => {
    expect(parseThemePreference("light")).toBe("light");
    expect(parseThemePreference("dark")).toBe("dark");
    expect(parseThemePreference("system")).toBe("system");
  });

  it("falls back to system for unknown values", () => {
    expect(parseThemePreference(null)).toBe("system");
    expect(parseThemePreference("weird")).toBe("system");
  });
});

describe("resolveTheme", () => {
  it("honours explicit light and dark", () => {
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });

  it("follows OS when preference is system", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
  });
});

describe("nextThemePreference", () => {
  it("cycles system → light → dark → system", () => {
    expect(nextThemePreference("system")).toBe("light");
    expect(nextThemePreference("light")).toBe("dark");
    expect(nextThemePreference("dark")).toBe("system");
  });
});

describe("themePreferenceLabel", () => {
  it("returns Russian labels", () => {
    expect(themePreferenceLabel("light")).toContain("светлая");
    expect(themePreferenceLabel("dark")).toContain("тёмная");
    expect(themePreferenceLabel("system")).toContain("системе");
  });
});
