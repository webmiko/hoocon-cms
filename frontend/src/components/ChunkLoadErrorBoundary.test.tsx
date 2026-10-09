import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChunkLoadErrorBoundary } from "./ChunkLoadErrorBoundary";
import { removeServerSeoTags } from "../utils/serverSeoTags";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const srcDir = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = (path: string) => readFileSync(join(srcDir, path), "utf8");

function Boom(): never {
  throw new Error("render failed");
}

let root: Root | null = null;
let host: HTMLDivElement | null = null;

afterEach(() => {
  act(() => root?.unmount());
  host?.remove();
  root = null;
  host = null;
  vi.restoreAllMocks();
});

describe("ChunkLoadErrorBoundary", () => {
  it("clears the error page when the route changes", () => {
    // One boundary for the whole app kept «Произошла ошибка» on every next page.
    vi.spyOn(console, "error").mockImplementation(() => {});
    host = document.createElement("div");
    document.body.appendChild(host);
    root = createRoot(host);
    act(() =>
      root?.render(
        <ChunkLoadErrorBoundary resetKey="/catalog">
          <Boom />
        </ChunkLoadErrorBoundary>,
      ),
    );
    expect(host.textContent).toContain("Произошла ошибка");

    act(() =>
      root?.render(
        <ChunkLoadErrorBoundary resetKey="/kontakty">
          <p>Контакты</p>
        </ChunkLoadErrorBoundary>,
      ),
    );
    expect(host.textContent).toBe("Контакты");
  });

  it("wraps the route outlet inside the shell, keyed by pathname", () => {
    expect(src("components/Layout.tsx")).toMatch(
      /<ChunkLoadErrorBoundary resetKey=\{location\.pathname\}>\s*<RouteSlideOutlet \/>/,
    );
  });
});

describe("server SEO tags", () => {
  it("drops the static head tags that <Seo> re-renders, keeps title and JSON-LD", () => {
    // React 19 hoists Helmet tags beside the static ones → two canonicals.
    const head = document.createElement("head");
    head.innerHTML = `
      <title>Static</title>
      <meta name="description" content="x">
      <meta name="robots" content="index, follow">
      <link rel="canonical" href="https://hoocon.ru/">
      <link rel="alternate" hreflang="ru" href="https://hoocon.ru/">
      <meta property="og:url" content="https://hoocon.ru/">
      <meta name="twitter:card" content="summary">
      <link rel="preload" as="image" href="/hero.webp">
      <script type="application/ld+json">{}</script>
      <meta name="viewport" content="width=device-width">`;
    expect(removeServerSeoTags(head)).toBe(6);
    expect(head.querySelectorAll('link[rel="canonical"], meta[property^="og:"]')).toHaveLength(0);
    expect(head.querySelector("title")).not.toBeNull();
    expect(head.querySelector('script[type="application/ld+json"]')).not.toBeNull();
    expect(head.querySelector('link[rel="preload"]')).not.toBeNull();
    expect(head.querySelector('meta[name="viewport"]')).not.toBeNull();
  });

  it("runs before the React root mounts", () => {
    const main = src("main.tsx");
    expect(main.indexOf("removeServerSeoTags();")).toBeGreaterThan(-1);
    expect(main.indexOf("removeServerSeoTags();")).toBeLessThan(main.indexOf("createRoot("));
  });
});

describe("ArticlePage body", () => {
  it("sanitizes the CMS body once (before TOC ids), not twice", () => {
    const page = src("pages/ArticlePage.tsx");
    expect(page.match(/sanitizeHtml\(/g)).toHaveLength(1);
    expect(page).toMatch(/extractArticleToc\(sanitizeHtml\(article\.body\)\)/);
  });
});
