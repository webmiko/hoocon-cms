import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { buildCookieConsent, writeCookieConsent } from "../utils/cookieConsent";
import { Analytics } from "./Analytics";

vi.mock("../utils/siteAnalytics", () => ({ trackSitePageView: vi.fn() }));

let container: HTMLDivElement;
let root: Root;
const reload = vi.fn();
const realLocation = window.location;

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  Object.defineProperty(window, "location", { configurable: true, value: { ...realLocation, reload } });
  writeCookieConsent(buildCookieConsent(true));
  container = document.createElement("div");
  root = createRoot(container);
  act(() =>
    root.render(
      <MemoryRouter>
        <Analytics />
      </MemoryRouter>,
    ),
  );
});

afterEach(() => {
  act(() => root.unmount());
  document.getElementById("ym-script")?.remove();
  Object.defineProperty(window, "location", { configurable: true, value: realLocation });
  localStorage.clear();
  reload.mockReset();
});

describe("Analytics consent withdrawal", () => {
  it("reloads the tab when Metrika (webvisor) is already running", () => {
    const script = document.createElement("script");
    script.id = "ym-script";
    document.head.appendChild(script);

    act(() => writeCookieConsent(buildCookieConsent(false)));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("does not reload when counters were never loaded", () => {
    act(() => writeCookieConsent(buildCookieConsent(false)));
    expect(reload).not.toHaveBeenCalled();
  });
});
