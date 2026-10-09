import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ArticlesListPage } from "./ArticlesListPage";

let container: HTMLDivElement;
let root: Root;

function article(id: number) {
  return { id, slug: `a-${id}`, title: `Статья ${id}`, excerpt: "", reading_minutes: id === 1 ? 7 : 0, published_at: null, cover: null };
}

async function flush() {
  await act(async () => {
    for (let i = 0; i < 5; i += 1) await Promise.resolve();
  });
}

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const second = String(url).includes("page=2");
      const body = second
        ? { count: 21, next: null, results: [article(21)] }
        : { count: 21, next: "/api/content/articles/?page=2", results: Array.from({ length: 20 }, (_, i) => article(i + 1)) };
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

describe("ArticlesListPage", () => {
  it("reaches the 21st article via «Показать ещё»", async () => {
    act(() =>
      root.render(
        <MemoryRouter>
          <ArticlesListPage />
        </MemoryRouter>,
      ),
    );
    await flush();
    expect(container.textContent).not.toContain("Статья 21");
    const button = Array.from(container.querySelectorAll("button")).find((b) => b.textContent === "Показать ещё");
    expect(button).toBeDefined();

    await act(async () => button!.click());
    await flush();
    expect(container.textContent).toContain("Статья 21");
    expect(container.textContent).not.toContain("Показать ещё");
  });

  it("shows reading time from the API field (the list no longer ships body)", async () => {
    act(() =>
      root.render(
        <MemoryRouter>
          <ArticlesListPage />
        </MemoryRouter>,
      ),
    );
    await flush();
    expect(container.textContent).toContain("7 мин чтения");
  });
});
