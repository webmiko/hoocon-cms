import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "./client";

const here = dirname(fileURLToPath(import.meta.url));
const comparePage = readFileSync(join(here, "..", "pages", "ComparePage.tsx"), "utf8");

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async () => new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api read methods forward AbortSignal to fetch", () => {
  const signal = new AbortController().signal;
  const calls: [string, () => Promise<unknown>][] = [
    ["categories", () => api.categories(signal)],
    ["skus", () => api.skus({ q: "da" }, signal)],
    ["quizAnalogs", () => api.quizAnalogs({ a: "1" }, signal)],
    ["facets", () => api.facets(undefined, signal)],
    ["compare", () => api.compare(["a"], signal)],
    ["docs", () => api.docs({}, signal)],
    ["pageDetail", () => api.pageDetail("faq", signal)],
    ["articles", () => api.articles(1, signal)],
    ["articleDetail", () => api.articleDetail("a", signal)],
    ["news", () => api.news({}, signal)],
    ["newsDetail", () => api.newsDetail("n", signal)],
    ["search", () => api.search("da", 1, signal)],
  ];
  it.each(calls)("%s", async (_name, call) => {
    await call();
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(init?.signal).toBe(signal);
  });
});

describe("compare add-search", () => {
  it("debounces the query and passes the abort signal (was one request per keystroke)", () => {
    expect(comparePage).toMatch(/useDebouncedValue\(addQuery\.trim\(\), COMPARE_SEARCH_DEBOUNCE_MS\)/);
    expect(comparePage).toMatch(/const COMPARE_SEARCH_DEBOUNCE_MS = 250;/);
    expect(comparePage).toMatch(/api\.skus\(\{ q: searchQuery, page_size: "12" \}, signal\)/);
  });
});
