import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";
import { registerSW } from "virtual:pwa-register";

import { PullToRefresh } from "./components/PullToRefresh";
import { ThemeProvider } from "./theme/ThemeProvider";
import "./styles/global.css";
import App from "./App";

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
