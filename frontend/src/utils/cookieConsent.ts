/**
 * Granular cookie consent (152-ФЗ / GDPR-style).
 *
 * Essential cookies are always on (site + CSRF/forms + first-party pageview
 * stats for Admin). Third-party analytics (Metrika/GA4) and marketing push
 * require explicit opt-in. Preference JSON in localStorage.
 */

export const COOKIE_CONSENT_STORAGE_KEY = "hoocon-cookie-consent";
export const COOKIE_CONSENT_VERSION = 2;
export const COOKIE_CONSENT_CHANGE_EVENT = "hoocon-cookie-consent";
export const COOKIE_CONSENT_OPEN_EVENT = "hoocon-cookie-consent-open";

export type CookieConsentState = {
  version: number;
  /** Always true — site operation, CSRF, form protection. Not user-togglable. */
  essential: true;
  /** Optional: Yandex Metrika / GA4 after explicit consent. */
  analytics: boolean;
  /** Optional: marketing / news Web Push (after Notification permission). */
  marketing: boolean;
  updatedAt: string;
};

/**
 * Build a consent snapshot.
 */
export function buildCookieConsent(
  analytics: boolean,
  marketing: boolean = false,
): CookieConsentState {
  return {
    version: COOKIE_CONSENT_VERSION,
    essential: true,
    analytics,
    marketing,
    updatedAt: new Date().toISOString(),
  };
}

/**
 * Parse stored consent, including legacy "accepted" / "declined" strings.
 */
export function parseCookieConsent(raw: string | null): CookieConsentState | null {
  if (raw === null || raw === "") {
    return null;
  }
  if (raw === "accepted") {
    return buildCookieConsent(true, false);
  }
  if (raw === "declined") {
    return buildCookieConsent(false, false);
  }
  try {
    const data = JSON.parse(raw) as Partial<CookieConsentState>;
    if (typeof data !== "object" || data === null) {
      return null;
    }
    if (typeof data.analytics !== "boolean") {
      return null;
    }
    return {
      version: COOKIE_CONSENT_VERSION,
      essential: true,
      analytics: data.analytics,
      marketing: typeof data.marketing === "boolean" ? data.marketing : false,
      updatedAt:
        typeof data.updatedAt === "string" && data.updatedAt
          ? data.updatedAt
          : new Date().toISOString(),
    };
  } catch {
    return null;
  }
}

/**
 * Read consent from localStorage.
 * Migrates legacy "accepted" / "declined" strings to JSON in place.
 */
export function readCookieConsent(): CookieConsentState | null {
  try {
    const raw = localStorage.getItem(COOKIE_CONSENT_STORAGE_KEY);
    if (raw === "accepted" || raw === "declined") {
      const migrated = parseCookieConsent(raw);
      if (migrated) {
        localStorage.setItem(
          COOKIE_CONSENT_STORAGE_KEY,
          JSON.stringify(migrated),
        );
      }
      return migrated;
    }
    const parsed = parseCookieConsent(raw);
    if (parsed && raw) {
      try {
        const data = JSON.parse(raw) as Partial<CookieConsentState>;
        if (typeof data.marketing !== "boolean") {
          localStorage.setItem(COOKIE_CONSENT_STORAGE_KEY, JSON.stringify(parsed));
        }
      } catch {
        /* ignore */
      }
    }
    return parsed;
  } catch {
    return null;
  }
}

/**
 * Persist consent and notify same-tab listeners.
 */
export function writeCookieConsent(state: CookieConsentState): void {
  try {
    localStorage.setItem(COOKIE_CONSENT_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Ignore write failures (private mode / quota).
  }
  window.dispatchEvent(
    new CustomEvent(COOKIE_CONSENT_CHANGE_EVENT, { detail: state }),
  );
}

/**
 * Whether analytics scripts may load.
 */
export function isAnalyticsAllowed(state: CookieConsentState | null): boolean {
  return state?.analytics === true;
}

/** Whether marketing Web Push may be offered / subscribed. */
export function isMarketingAllowed(state: CookieConsentState | null): boolean {
  return state?.marketing === true;
}

/** Ask CookieConsent UI to open the preferences panel. */
export function openCookieConsentSettings(): void {
  window.dispatchEvent(new Event(COOKIE_CONSENT_OPEN_EVENT));
}
