import { afterEach, describe, expect, it, vi } from "vitest";

import {
  clearProtectedMediaSrcCacheForTests,
  resolveProtectedMediaSrc,
} from "./protectedMediaSrc";

afterEach(() => {
  clearProtectedMediaSrcCacheForTests();
  vi.unstubAllGlobals();
});

describe("resolveProtectedMediaSrc", () => {
  it("returns opaque URLs unchanged", async () => {
    await expect(resolveProtectedMediaSrc("blob:http://x/1")).resolves.toBe(
      "blob:http://x/1",
    );
    await expect(resolveProtectedMediaSrc("data:image/png;base64,xx")).resolves.toBe(
      "data:image/png;base64,xx",
    );
  });

  it("fetches media and returns a blob URL", async () => {
    const blob = new Blob([new Uint8Array([1, 2, 3])], { type: "image/webp" });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      blob: async () => blob,
    });
    vi.stubGlobal("fetch", fetchMock);
    const createObjectURL = vi.fn().mockReturnValue("blob:http://test/obj");
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL: vi.fn() });

    const first = await resolveProtectedMediaSrc("/media/product_images/a.webp");
    const second = await resolveProtectedMediaSrc("/media/product_images/a.webp");

    expect(first).toBe("blob:http://test/obj");
    expect(second).toBe("blob:http://test/obj");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/media/product_images/a.webp",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("rejects when fetch is not ok", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 404 }),
    );
    await expect(
      resolveProtectedMediaSrc("/media/missing.webp"),
    ).rejects.toThrow(/404/);
  });
});
