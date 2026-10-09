import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ThemeContext, type ThemeContextValue } from "../theme/ThemeContext";
import { ThemeAwareCover } from "./ThemeAwareCover";

let container: HTMLDivElement;
let root: Root;

function theme(resolved: "light" | "dark"): ThemeContextValue {
  return { preference: resolved, resolved, label: "", setPreference: () => {}, cyclePreference: () => {} };
}

function render(resolved: "light" | "dark", dark: string | null = "/c-dark.webp") {
  act(() =>
    root.render(
      <ThemeContext.Provider value={theme(resolved)}>
        <ThemeAwareCover light="/c-light.webp" dark={dark} loading="eager" />
      </ThemeContext.Provider>,
    ),
  );
  return Array.from(container.querySelectorAll("img"));
}

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
});

describe("ThemeAwareCover", () => {
  it("renders one image so only one cover is downloaded (was light+dark eager)", () => {
    const imgs = render("light");
    expect(imgs).toHaveLength(1);
    expect(imgs[0].getAttribute("src")).toBe("/c-light.webp");
    expect(imgs[0].getAttribute("fetchpriority")).toBe("high");
  });

  it("uses the dark asset in dark theme and falls back to light without one", () => {
    expect(render("dark")[0].getAttribute("src")).toBe("/c-dark.webp");
    expect(render("dark", null)[0].getAttribute("src")).toBe("/c-light.webp");
  });
});
