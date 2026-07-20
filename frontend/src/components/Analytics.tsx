/**
 * Load Yandex Metrika / GA4 only after explicit analytics consent (БЗ §8.6).
 *
 * Counter IDs: GET /api/settings/public/ (Admin SiteSettings), fallback to Vite env.
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

type PublicAnalyticsIds = {
  yandex_metrika_id: string;
  ga4_measurement_id: string;
};

let cachedIds: PublicAnalyticsIds | null = null;
let idsPromise: Promise<PublicAnalyticsIds> | null = null;

async function fetchAnalyticsIds(): Promise<PublicAnalyticsIds> {
  if (cachedIds) {
    return cachedIds;
  }
  if (!idsPromise) {
    idsPromise = (async () => {
      const fallback: PublicAnalyticsIds = {
        yandex_metrika_id:
          (import.meta.env.VITE_YANDEX_METRIKA_ID as string | undefined) || "",
        ga4_measurement_id:
          (import.meta.env.VITE_GA4_MEASUREMENT_ID as string | undefined) || "",
      };
      try {
        const response = await fetch("/api/settings/public/", {
          credentials: "omit",
        });
        if (!response.ok) {
          return fallback;
        }
        const data = (await response.json()) as Partial<PublicAnalyticsIds>;
        cachedIds = {
          yandex_metrika_id:
            (data.yandex_metrika_id || "").trim() || fallback.yandex_metrika_id,
          ga4_measurement_id:
            (data.ga4_measurement_id || "").trim() || fallback.ga4_measurement_id,
        };
        return cachedIds;
      } catch {
        return fallback;
      }
    })();
  }
  return idsPromise;
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

async function tryLoadAnalytics(): Promise<void> {
  if (!isAnalyticsAllowed(readCookieConsent())) {
    return;
  }
  const ids = await fetchAnalyticsIds();
  if (ids.yandex_metrika_id) {
    loadYandexMetrika(ids.yandex_metrika_id);
  }
  if (ids.ga4_measurement_id) {
    loadGa4(ids.ga4_measurement_id);
  }
}

/**
 * Mount once in Layout: loads analytics only when analytics category is allowed.
 */
export function Analytics() {
  useEffect(() => {
    void tryLoadAnalytics();

    function onStorage(event: StorageEvent) {
      if (event.key !== COOKIE_CONSENT_STORAGE_KEY) {
        return;
      }
      if (isAnalyticsAllowed(parseCookieConsent(event.newValue))) {
        void tryLoadAnalytics();
      }
    }

    function onConsentChange() {
      void tryLoadAnalytics();
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
