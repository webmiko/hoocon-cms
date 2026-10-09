import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { act, useRef, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { useFocusTrap } from "./useFocusTrap";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const srcDir = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = (path: string) => readFileSync(join(srcDir, path), "utf8");

function SwitchingDialog() {
  const [mode, setMode] = useState<"banner" | "settings">("banner");
  const ref = useRef<HTMLDivElement>(null);
  useFocusTrap(ref, true, mode);
  if (mode === "banner") {
    return (
      <div ref={ref}>
        <p>Cookie</p>
        <div>
          <button type="button" id="open" onClick={() => setMode("settings")}>
            Настроить
          </button>
        </div>
      </div>
    );
  }
  return (
    <div ref={ref}>
      <h2>Настройки</h2>
      <button type="button" id="first">
        Первая
      </button>
      <button type="button" id="last">
        Последняя
      </button>
    </div>
  );
}

let root: Root | null = null;
let host: HTMLDivElement | null = null;

afterEach(() => {
  act(() => root?.unmount());
  host?.remove();
  root = null;
  host = null;
});

describe("useFocusTrap", () => {
  it("moves focus into the settings panel when the banner switches while active", () => {
    // «Настроить» unmounts itself; with active still true the trap never re-ran
    // and keyboard focus fell to <body> outside the modal.
    host = document.createElement("div");
    document.body.appendChild(host);
    root = createRoot(host);
    act(() => root?.render(<SwitchingDialog />));
    const open = host.querySelector("#open") as HTMLButtonElement;
    open.focus();
    act(() => open.click());
    expect(document.activeElement).toBe(host.querySelector("#first"));

    const last = host.querySelector("#last") as HTMLButtonElement;
    last.focus();
    act(() => {
      last.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true }));
    });
    expect(document.activeElement).toBe(host.querySelector("#first"));
  });

  it("is wired into the cookie panel and the mobile menu", () => {
    expect(src("components/CookieConsent.tsx")).toMatch(
      /useFocusTrap\(panelRef, mode !== "hidden", mode\)/,
    );
    const layout = src("components/Layout.tsx");
    expect(layout).toMatch(/useFocusTrap\(menuPanelRef, menuOpen\)/);
    expect(layout).toMatch(/ref=\{menuPanelRef\}\s+id=\{menuId\}/);
  });
});

describe("site search navigation", () => {
  it("goes straight to /search without the slash redirect (one page view)", () => {
    const layout = src("components/Layout.tsx");
    expect(layout).not.toMatch(/navigate\(`\/search\/\?/);
    expect(layout).toMatch(/navigate\(`\/search\?q=/);
  });

  it("remounts the search input when the query changes", () => {
    expect(src("pages/SearchPage.tsx")).toMatch(/<input\s+key=\{q\}[\s\S]*?defaultValue=\{q\}/);
  });
});
