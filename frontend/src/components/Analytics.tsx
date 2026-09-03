/**
 * Load Yandex Metrika / GA4 only after explicit analytics consent (БЗ §8.6).
 *
 * Counter IDs: GET /api/settings/public/ (Admin SiteSettings), fallback to Vite env
 * / production defaults. Scripts start after ANALYTICS_DELAY_MS (LCP-friendly).
 * SPA hits + lead goals: utils/analyticsTrack.ts.
 */

import { useEffect } from "react";
import { useLocation } from "react-router-dom";

import {
  setAnalyticsCounters,
  trackSpaHit,
} from "../utils/analyticsTrack";
import { trackSitePageView } from "../utils/siteAnalytics";
import { yandexMetrikaInitOptions } from "../utils/yandexMetrikaInit";
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

/** Defer counter scripts after consent to protect LCP/INP. */
export const ANALYTICS_DELAY_MS = 3000;

/** Production defaults (public counter IDs; Admin / env override). */
const DEFAULT_YANDEX_METRIKA_ID = "73321399";
const DEFAULT_GA4_MEASUREMENT_ID = "G-DLRV7BZ5JP";

type PublicAnalyticsIds = {
  yandex_metrika_id: string;
  ga4_measurement_id: string;
};

let cachedIds: PublicAnalyticsIds | null = null;
let idsPromise: Promise<PublicAnalyticsIds> | null = null;
let loadTimer: ReturnType<typeof setTimeout> | null = null;
let scriptsRequested = false;

function viteFallbackIds(): PublicAnalyticsIds {
  return {
    yandex_metrika_id:
      (import.meta.env.VITE_YANDEX_METRIKA_ID as string | undefined)?.trim()
      || DEFAULT_YANDEX_METRIKA_ID,
    ga4_measurement_id:
      (import.meta.env.VITE_GA4_MEASUREMENT_ID as string | undefined)?.trim()
      || DEFAULT_GA4_MEASUREMENT_ID,
  };
}

async function fetchAnalyticsIds(): Promise<PublicAnalyticsIds> {
  if (cachedIds) {
    return cachedIds;
  }
  if (!idsPromise) {
    idsPromise = (async () => {
      const fallback = viteFallbackIds();
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
    window.dataLayer = window.dataLayer ?? [];
    window.ym?.(id, "init", yandexMetrikaInitOptions());
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

function clearPendingLoad(): void {
  if (loadTimer !== null) {
    clearTimeout(loadTimer);
    loadTimer = null;
  }
}

/**
 * Schedule counter load after ANALYTICS_DELAY_MS when analytics cookies allowed.
 */
function scheduleAnalyticsLoad(): void {
  if (!isAnalyticsAllowed(readCookieConsent())) {
    clearPendingLoad();
    return;
  }
  if (scriptsRequested) {
    return;
  }
  if (loadTimer !== null) {
    return;
  }
  loadTimer = setTimeout(() => {
    loadTimer = null;
    void (async () => {
      if (!isAnalyticsAllowed(readCookieConsent())) {
        return;
      }
      if (scriptsRequested) {
        return;
      }
      scriptsRequested = true;
      const ids = await fetchAnalyticsIds();
      setAnalyticsCounters(ids.yandex_metrika_id, ids.ga4_measurement_id);
      if (ids.yandex_metrika_id) {
        loadYandexMetrika(ids.yandex_metrika_id);
      }
      if (ids.ga4_measurement_id) {
        loadGa4(ids.ga4_measurement_id);
      }
    })();
  }, ANALYTICS_DELAY_MS);
}

/**
 * Mount once in Layout: loads third-party analytics when allowed (deferred);
 * always records first-party SPA pageviews (essential cookies).
 */
export function Analytics() {
  const location = useLocation();
  const routeKey = `${location.pathname}${location.search}`;

  useEffect(() => {
    scheduleAnalyticsLoad();

    function onStorage(event: StorageEvent) {
      if (event.key !== COOKIE_CONSENT_STORAGE_KEY) {
        return;
      }
      if (isAnalyticsAllowed(parseCookieConsent(event.newValue))) {
        scheduleAnalyticsLoad();
      }
    }

    function onConsentChange() {
      scheduleAnalyticsLoad();
    }

    window.addEventListener("storage", onStorage);
    window.addEventListener(COOKIE_CONSENT_CHANGE_EVENT, onConsentChange);
    return () => {
      clearPendingLoad();
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(COOKIE_CONSENT_CHANGE_EVENT, onConsentChange);
    };
  }, []);

  useEffect(() => {
    // First-party Admin stats — always (essential session cookie).
    trackSitePageView(routeKey);
    // Third-party Metrika/GA4 — only after opt-in (see scheduleAnalyticsLoad).
    trackSpaHit(routeKey);
  }, [routeKey]);

  return null;
}
