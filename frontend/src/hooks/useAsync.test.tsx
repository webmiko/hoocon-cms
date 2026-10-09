import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { setAsyncCache } from "../utils/asyncDataCache";
import { useAsync } from "./useAsync";

type Snapshot = { data: string | undefined; loading: boolean; error: string | undefined };

interface Deferred {
  resolve: (value: string) => void;
  reject: (err: Error) => void;
}

const pending = new Map<string, Deferred>();
let renders: Array<Snapshot & { slug: string }> = [];

function fetchSlug(slug: string): Promise<string> {
  return new Promise((resolve, reject) => {
    pending.set(slug, { resolve, reject });
  });
}

function Probe({ slug, cache }: { slug: string; cache?: boolean }) {
  const { data, loading, error } = useAsync(
    () => fetchSlug(slug),
    slug,
    cache ? `test:sku:${slug}` : undefined,
  );
  renders.push({ slug, data, loading, error: error?.message });
  return null;
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  root = createRoot(container);
  pending.clear();
  renders = [];
});

afterEach(() => {
  act(() => root.unmount());
});

async function settle(slug: string, outcome: string | Error) {
  await act(async () => {
    const deferred = pending.get(slug)!;
    if (outcome instanceof Error) deferred.reject(outcome);
    else deferred.resolve(outcome);
  });
}

describe("useAsync key changes", () => {
  it("never renders data of the previous key (A→B shows loading, not A)", async () => {
    act(() => root.render(<Probe slug="a" />));
    await settle("a", "card-A");
    renders = [];

    act(() => root.render(<Probe slug="b" />));
    const forB = renders.filter((r) => r.slug === "b");
    expect(forB.length).toBeGreaterThan(0);
    expect(forB.every((r) => r.data !== "card-A")).toBe(true);
    expect(forB[forB.length - 1]).toMatchObject({ data: undefined, loading: true });

    await settle("b", "card-B");
    expect(renders[renders.length - 1]).toMatchObject({ slug: "b", data: "card-B", loading: false });
  });

  it("404 on B does not fall back to A's data", async () => {
    act(() => root.render(<Probe slug="a" />));
    await settle("a", "card-A");
    act(() => root.render(<Probe slug="b" />));
    await settle("b", new Error("API 404"));
    expect(renders[renders.length - 1]).toMatchObject({
      slug: "b",
      data: undefined,
      loading: false,
      error: "API 404",
    });
  });

  it("uses the session cache of the new key immediately", async () => {
    setAsyncCache("test:sku:b", "cached-B");
    act(() => root.render(<Probe slug="a" cache />));
    await settle("a", "card-A");
    renders = [];
    act(() => root.render(<Probe slug="b" cache />));
    const first = renders.find((r) => r.slug === "b");
    expect(first).toMatchObject({ data: "cached-B", loading: false });
  });
});
