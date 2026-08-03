import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";
import { registerSW } from "virtual:pwa-register";

import { PullToRefresh } from "./components/PullToRefresh";
import { ThemeProvider } from "./theme/ThemeProvider";
import { HOOCON_MAIN_CSS_ID } from "./hooconMainCss";
import "./styles/global.css";
import App from "./App";
import {
  clearChunkReloadFlag,
  recoverFromStaleChunk,
} from "./utils/chunkLoadRecovery";

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

promoteMainStylesheet();

// Home is eager — clear the one-shot guard once the shell stays healthy.
window.setTimeout(() => {
  clearChunkReloadFlag();
}, 10_000);

window.addEventListener("unhandledrejection", (event) => {
  if (recoverFromStaleChunk(event.reason)) {
    event.preventDefault();
  }
});

registerSW({
  immediate: true,
  onRegisteredSW(_swUrl, registration) {
    if (!registration) return;
    // Pick up new builds while a tab stays open (deploy race).
    window.setInterval(() => {
      void registration.update();
    }, 60 * 60 * 1000);
  },
});

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
