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
