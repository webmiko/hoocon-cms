import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";
import { registerSW } from "virtual:pwa-register";

import { api } from "./api/client";
import { PullToRefresh } from "./components/PullToRefresh";
import { ThemeProvider } from "./theme/ThemeProvider";
import "./styles/global.css";
import App from "./App";

registerSW({ immediate: true });

// CSRF after first paint — keeps /api/csrf/ off the critical request chain
// (Lighthouse). Spec: ПЛАН §6 Iter 4 — F8 (CSRF).
function scheduleIdle(task: () => void): void {
  if (typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(() => task(), { timeout: 2500 });
    return;
  }
  window.setTimeout(task, 1);
}

scheduleIdle(() => {
  void api.fetchCsrfToken().catch((err) => {
    console.warn("CSRF token fetch failed:", err);
  });
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
