import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CHUNK_RELOAD_STORAGE_KEY,
  clearChunkReloadFlag,
  isChunkLoadError,
  recoverFromStaleChunk,
} from "./chunkLoadRecovery";

afterEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("isChunkLoadError", () => {
  it("matches Vite dynamic import failures", () => {
    expect(
      isChunkLoadError(
        new TypeError(
          "Failed to fetch dynamically imported module: https://example/a.js",
        ),
      ),
    ).toBe(true);
    expect(
      isChunkLoadError(
        new Error("Importing a module script failed."),
      ),
    ).toBe(true);
    expect(isChunkLoadError(new Error("Loading chunk foo failed"))).toBe(true);
  });

  it("rejects unrelated errors", () => {
    expect(isChunkLoadError(new Error("Network offline"))).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
  });
});

describe("recoverFromStaleChunk", () => {
  it("reloads once then refuses a second time", () => {
    const reload = vi.fn();
    const err = new TypeError(
      "Failed to fetch dynamically imported module: /assets/x.js",
    );

    expect(recoverFromStaleChunk(err, reload)).toBe(true);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem(CHUNK_RELOAD_STORAGE_KEY)).toBe("1");

    expect(recoverFromStaleChunk(err, reload)).toBe(false);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("ignores non-chunk errors", () => {
    const reload = vi.fn();
    expect(recoverFromStaleChunk(new Error("boom"), reload)).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });

  it("clearChunkReloadFlag allows another attempt", () => {
    const reload = vi.fn();
    const err = new TypeError(
      "Failed to fetch dynamically imported module: /assets/x.js",
    );
    recoverFromStaleChunk(err, reload);
    clearChunkReloadFlag();
    expect(recoverFromStaleChunk(err, reload)).toBe(true);
    expect(reload).toHaveBeenCalledTimes(2);
  });
});
