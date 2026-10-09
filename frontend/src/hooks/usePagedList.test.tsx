import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { usePagedList, type PagedResponse } from "./usePagedList";

type Row = { id: number };

let container: HTMLDivElement;
let root: Root;
type PagedState = ReturnType<typeof usePagedList<Row>>;
let latest: PagedState;
const capture = (state: PagedState) => {
  latest = state;
};

function Probe({
  fetchPage,
  k,
  onState = capture,
}: {
  fetchPage: (page: number) => Promise<PagedResponse<Row>>;
  k: string;
  onState?: (state: PagedState) => void;
}) {
  onState(usePagedList<Row>((page) => fetchPage(page), k));
  return null;
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

function rows(from: number, to: number): Row[] {
  return Array.from({ length: to - from + 1 }, (_, i) => ({ id: from + i }));
}

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
});

describe("usePagedList", () => {
  it("loads pages after the first 20 (21st article was unreachable)", async () => {
    const fetchPage = vi.fn(async (page: number) =>
      page === 1 ? { results: rows(1, 20), next: "/api/?page=2" } : { results: rows(21, 23), next: null },
    );
    act(() => root.render(<Probe fetchPage={fetchPage} k="all" />));
    await flush();
    expect(latest.items).toHaveLength(20);
    expect(latest.hasNext).toBe(true);

    await act(async () => latest.loadMore());
    expect(fetchPage).toHaveBeenLastCalledWith(2);
    expect(latest.items.map((r) => r.id).at(-1)).toBe(23);
    expect(latest.hasNext).toBe(false);
  });

  it("dedupes rows shifted by a new publication", async () => {
    const fetchPage = vi.fn(async (page: number) =>
      page === 1 ? { results: rows(1, 20), next: "n" } : { results: rows(20, 22), next: null },
    );
    act(() => root.render(<Probe fetchPage={fetchPage} k="all" />));
    await flush();
    await act(async () => latest.loadMore());
    expect(latest.items.map((r) => r.id)).toEqual(rows(1, 22).map((r) => r.id));
  });

  it("drops appended pages when the filter key changes", async () => {
    const fetchPage = vi.fn(async (page: number) =>
      page === 1 ? { results: rows(1, 20), next: "n" } : { results: rows(21, 25), next: null },
    );
    act(() => root.render(<Probe fetchPage={fetchPage} k="a" />));
    await flush();
    await act(async () => latest.loadMore());
    expect(latest.items).toHaveLength(25);

    const other = vi.fn(async () => ({ results: rows(100, 101), next: null }));
    act(() => root.render(<Probe fetchPage={other} k="b" />));
    await flush();
    expect(latest.items.map((r) => r.id)).toEqual([100, 101]);
    expect(latest.hasNext).toBe(false);
  });

  it("treats a bare array as a single page", async () => {
    act(() => root.render(<Probe fetchPage={async () => rows(1, 3)} k="x" />));
    await flush();
    expect(latest.items).toHaveLength(3);
    expect(latest.hasNext).toBe(false);
  });
});
