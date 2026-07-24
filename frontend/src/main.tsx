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

// Fetch the CSRF token cookie once on app load so that POST /api/leads/
// can send the X-CSRFToken header. Spec: ПЛАН §6 Iter 4 — F8 (CSRF).
void api.fetchCsrfToken().catch((err) => {
  // Non-fatal: the leads endpoint will still work via honeypot + throttle
  // for anonymous users; CSRF is enforced only for session-authenticated
  // requests. Log to console for dev visibility.
  console.warn("CSRF token fetch failed:", err);
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
