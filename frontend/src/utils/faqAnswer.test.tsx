import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { faqAnswerNodes } from "./faqAnswer";

let container: HTMLDivElement;
let root: Root;

function render(text: string): HTMLAnchorElement[] {
  act(() => root.render(<MemoryRouter>{faqAnswerNodes(text)}</MemoryRouter>));
  return Array.from(container.querySelectorAll("a"));
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

describe("faqAnswerNodes", () => {
  it("keeps slashes inside words as plain text (AC/DC, MU/FU)", () => {
    const text = "Питание AC/DC 24 В, серии MU/FU и on/off.";
    expect(render(text)).toHaveLength(0);
    expect(container.textContent).toBe(text);
  });

  it("does not link unknown top-level paths", () => {
    expect(render("Смотрите /admin и /api/leads.")).toHaveLength(0);
  });

  it("links real site routes and keeps trailing punctuation", () => {
    const links = render("Каталог: /catalog/sharovye-krany, статьи /statyi. Цена — /rfq?sku=DA24.");
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "/catalog/sharovye-krany",
      "/statyi",
      "/rfq?sku=DA24",
    ]);
    expect(container.textContent).toContain("статьи");
    expect(container.textContent?.endsWith(".")).toBe(true);
  });

  it("links a path at the start of text or after an opening bracket", () => {
    const links = render("/consultation (или /kontakty)");
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["/consultation", "/kontakty"]);
  });
});
