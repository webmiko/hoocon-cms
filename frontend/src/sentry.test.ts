import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it, vi } from "vitest";

const sentryInit = vi.hoisted(() => vi.fn());
const browserTracingIntegration = vi.hoisted(() => vi.fn(() => ({})));

vi.mock("@sentry/react", () => ({
  init: sentryInit,
  browserTracingIntegration,
}));

describe("initSentry", () => {
  it("does not call Sentry.init without VITE_SENTRY_DSN", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "");
    vi.resetModules();
    const { initSentry } = await import("./sentry");
    initSentry();
    expect(sentryInit).not.toHaveBeenCalled();
  });

  it("initializes Sentry when VITE_SENTRY_DSN is set", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "https://example@o0.ingest.sentry.io/1");
    vi.stubEnv("VITE_SENTRY_TRACES_SAMPLE_RATE", "0.1");
    vi.resetModules();
    const { initSentry } = await import("./sentry");
    initSentry();
    expect(sentryInit).toHaveBeenCalledOnce();
    expect(sentryInit.mock.calls[0]?.[0]?.dsn).toBe(
      "https://example@o0.ingest.sentry.io/1",
    );
  });

  it("is wired from main.tsx before React mount", () => {
    const mainSource = readFileSync(
      resolve(import.meta.dirname, "main.tsx"),
      "utf8",
    );
    expect(mainSource).toMatch(/import \{ initSentry \} from "\.\/sentry"/);
    expect(mainSource).toMatch(/initSentry\(\);\n[\s\S]*createRoot\(document\.getElementById\("root"\)/);
  });
});
