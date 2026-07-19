/**
 * Load Yandex Metrika / GA4 only after explicit analytics consent (БЗ §8.6).
 *
 * Counter IDs come from Vite env (VITE_YANDEX_METRIKA_ID, VITE_GA4_MEASUREMENT_ID).
 * Essential cookies never require this gate.
 */

import { useEffect } from "react";

import {
  COOKIE_CONSENT_CHANGE_EVENT,
  COOKIE_CONSENT_STORAGE_KEY,
  isAnalyticsAllowed,
  parseCookieConsent,
  readCookieConsent,
} from "../utils/cookieConsent";

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
    ym?: (id: number, method: string, ...args: unknown[]) => void;
  }
}

function loadYandexMetrika(counterId: string): void {
  const id = Number(counterId);
  if (!Number.isFinite(id) || id <= 0) {
    return;
  }
  if (document.getElementById("ym-script")) {
    return;
  }
  const script = document.createElement("script");
  script.id = "ym-script";
  script.async = true;
  script.src = "https://mc.yandex.ru/metrika/tag.js";
  script.onload = () => {
    window.ym?.(id, "init", {
      clickmap: true,
      trackLinks: true,
      accurateTrackBounce: true,
    });
  };
  document.head.appendChild(script);
}

function loadGa4(measurementId: string): void {
  if (!measurementId.startsWith("G-")) {
    return;
  }
  if (document.getElementById("ga4-script")) {
    return;
  }
  const script = document.createElement("script");
  script.id = "ga4-script";
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`;
  document.head.appendChild(script);
  window.dataLayer = window.dataLayer ?? [];
  window.gtag = function gtag(...args: unknown[]) {
    window.dataLayer?.push(args);
  };
  window.gtag("js", new Date());
  window.gtag("config", measurementId);
}

function tryLoadAnalytics(): void {
  if (!isAnalyticsAllowed(readCookieConsent())) {
    return;
  }
  const ymId = import.meta.env.VITE_YANDEX_METRIKA_ID as string | undefined;
  const gaId = import.meta.env.VITE_GA4_MEASUREMENT_ID as string | undefined;
  if (ymId) {
    loadYandexMetrika(ymId);
  }
  if (gaId) {
    loadGa4(gaId);
  }
}

/**
 * Mount once in Layout: loads analytics only when analytics category is allowed.
 */
export function Analytics() {
  useEffect(() => {
    tryLoadAnalytics();

    function onStorage(event: StorageEvent) {
      if (event.key !== COOKIE_CONSENT_STORAGE_KEY) {
        return;
      }
      if (isAnalyticsAllowed(parseCookieConsent(event.newValue))) {
        tryLoadAnalytics();
      }
    }

    function onConsentChange() {
      tryLoadAnalytics();
    }

    window.addEventListener("storage", onStorage);
    window.addEventListener(COOKIE_CONSENT_CHANGE_EVENT, onConsentChange);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(COOKIE_CONSENT_CHANGE_EVENT, onConsentChange);
    };
  }, []);

  return null;
}
