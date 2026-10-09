import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ApiError } from "../api/client";
import { ContentUnavailable } from "./ContentUnavailable";

const here = dirname(fileURLToPath(import.meta.url));
let container: HTMLDivElement;
let root: Root;

async function render(error: unknown) {
  await act(async () => {
    root.render(
      <HelmetProvider>
        <MemoryRouter>
          <ContentUnavailable error={error} notFoundTitle="Статья не найдена" backTo="/statyi" backLabel="← Все статьи" />
        </MemoryRouter>
      </HelmetProvider>,
    );
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

function robots(): string | null {
  return document.head.querySelector('meta[name="robots"]')?.getAttribute("content") ?? null;
}

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("detail pages use ContentUnavailable for missing content", () => {
  it.each(["ArticlePage.tsx", "NewsPage.tsx", "PageView.tsx"])("%s", (file) => {
    const src = readFileSync(join(here, "..", "pages", file), "utf8");
    expect(src).toContain("<ContentUnavailable");
    expect(src).not.toMatch(/<h1>(Статья|Новость|Страница) не найдена<\/h1>/);
  });
});

describe("ContentUnavailable", () => {
  it("marks a missing article noindex (was a soft 404 without robots)", async () => {
    await render(new ApiError(404, { detail: "Not found." }));
    expect(container.querySelector("h1")?.textContent).toBe("Статья не найдена");
    expect(robots()).toMatch(/noindex/);
  });

  it("does not call a network/5xx failure «не найдено» and offers a retry", async () => {
    await render(new TypeError("Failed to fetch"));
    expect(container.querySelector("h1")?.textContent).toBe("Не удалось загрузить страницу");
    expect(container.querySelector("button")?.textContent).toBe("попробуйте ещё раз");
    expect(robots()).toMatch(/noindex/);

    await render(new ApiError(503, {}));
    expect(container.querySelector("h1")?.textContent).toBe("Не удалось загрузить страницу");
  });
});
