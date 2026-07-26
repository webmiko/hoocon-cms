import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";
import { registerSW } from "virtual:pwa-register";

import { PullToRefresh } from "./components/PullToRefresh";
import { ThemeProvider } from "./theme/ThemeProvider";
import {
  HOOCON_MAIN_CSS_ID,
  HOOCON_SPLASH_FADE_MS,
  HOOCON_SPLASH_ID,
  isSplashViewport,
  splashRemainingDwellMs,
} from "./hooconMainCss";
import "./styles/global.css";
import App from "./App";

/**
 * Entry CSS ships as ``media="print"`` (non-blocking). Flip to screen once
 * this module runs — same moment React mounts, no CSP inline handlers.
 */
function promoteMainStylesheet(): void {
  const link = document.getElementById(HOOCON_MAIN_CSS_ID);
  if (link instanceof HTMLLinkElement) {
    link.media = "all";
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

/** Resolve when the document and webfonts are fully loaded. */
function whenDocumentFullyLoaded(): Promise<void> {
  const loadDone =
    document.readyState === "complete"
      ? Promise.resolve()
      : new Promise<void>((resolve) => {
          window.addEventListener("load", () => resolve(), { once: true });
        });
  const fontsReady =
    document.fonts && typeof document.fonts.ready?.then === "function"
      ? document.fonts.ready.then(() => undefined)
      : Promise.resolve();
  return Promise.all([loadDone, fontsReady]).then(() => undefined);
}

/**
 * Mobile only: keep splash until loaded + min dwell, then fade.
 * Desktop: remove immediately (CSS already hides it ≥961px).
 */
function dismissBootSplash(): void {
  const splash = document.getElementById(HOOCON_SPLASH_ID);
  if (!(splash instanceof HTMLElement)) {
    return;
  }

  if (!isSplashViewport()) {
    splash.remove();
    return;
  }

  void (async () => {
    await whenDocumentFullyLoaded();
    // Ensure React's first paint can land under the splash before we fade.
    await new Promise<void>((resolve) => {
      if (typeof requestAnimationFrame !== "function") {
        resolve();
        return;
      }
      requestAnimationFrame(() => {
        requestAnimationFrame(() => resolve());
      });
    });

    const waitMore = splashRemainingDwellMs(performance.now());
    if (waitMore > 0) {
      await delay(waitMore);
    }

    splash.setAttribute("aria-busy", "false");
    splash.dataset.done = "";
    await delay(HOOCON_SPLASH_FADE_MS);
    splash.remove();
  })();
}

promoteMainStylesheet();
registerSW({ immediate: true });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <HelmetProvider>
      <BrowserRouter useTransitions={false}>
        <ThemeProvider>
          <PullToRefresh>
            <App />
          </PullToRefresh>
        </ThemeProvider>
      </BrowserRouter>
    </HelmetProvider>
  </StrictMode>,
);

dismissBootSplash();
