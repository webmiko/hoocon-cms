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
import { reloadIfReleaseStale } from "./utils/reloadIfReleaseStale";
import { installSupportChatControl } from "./utils/supportChatControl";

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
installSupportChatControl();

// Home is eager — clear the one-shot guard once the shell stays healthy.
window.setTimeout(() => {
  clearChunkReloadFlag();
}, 10_000);

window.addEventListener("unhandledrejection", (event) => {
  if (recoverFromStaleChunk(event.reason)) {
    event.preventDefault();
  }
});

if (import.meta.env.PROD) {
  let swRegistration: ServiceWorkerRegistration | undefined;
  const checkRelease = () => {
    void reloadIfReleaseStale();
  };
  const poke = () => {
    void swRegistration?.update();
    checkRelease();
  };
  checkRelease();
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") poke();
  });
  registerSW({
    immediate: true,
    onRegisteredSW(_swUrl, registration) {
      swRegistration = registration;
      if (!registration) return;
      window.setInterval(poke, 5 * 60 * 1000);
    },
  });
}

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
