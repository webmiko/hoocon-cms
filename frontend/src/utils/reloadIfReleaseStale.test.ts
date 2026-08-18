import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RELEASE_VERSION } from "../release";
import {
  RELEASE_RELOAD_STORAGE_KEY,
  reloadIfReleaseStale,
} from "./reloadIfReleaseStale";

const memory = new Map<string, string>();

beforeEach(() => {
  memory.clear();
  vi.stubGlobal("sessionStorage", {
    getItem: (key: string) => memory.get(key) ?? null,
    setItem: (key: string, value: string) => {
      memory.set(key, value);
    },
    removeItem: (key: string) => {
      memory.delete(key);
    },
    clear: () => {
      memory.clear();
    },
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("reloadIfReleaseStale", () => {
  it("does nothing when health matches this bundle", async () => {
    const reload = vi.fn();
    const did = await reloadIfReleaseStale(
      async () => ({ version: RELEASE_VERSION }),
      reload,
    );
    expect(did).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });

  it("reloads once when health reports another version", async () => {
    const reload = vi.fn();
    const did = await reloadIfReleaseStale(
      async () => ({ version: "9.9.9" }),
      reload,
    );
    expect(did).toBe(true);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem(RELEASE_RELOAD_STORAGE_KEY)).toBe("9.9.9");

    const again = await reloadIfReleaseStale(
      async () => ({ version: "9.9.9" }),
      reload,
    );
    expect(again).toBe(false);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("ignores health fetch failures", async () => {
    const reload = vi.fn();
    const did = await reloadIfReleaseStale(async () => {
      throw new Error("offline");
    }, reload);
    expect(did).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });
});
