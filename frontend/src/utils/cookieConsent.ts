/**
 * Granular cookie consent (152-ФЗ / GDPR-style).
 *
 * Essential cookies are always on (site + CSRF/forms). Analytics (Metrika/GA4)
 * loads only after explicit opt-in. Preference JSON lives in localStorage.
 */

export const COOKIE_CONSENT_STORAGE_KEY = "hoocon-cookie-consent";
export const COOKIE_CONSENT_VERSION = 1;
export const COOKIE_CONSENT_CHANGE_EVENT = "hoocon-cookie-consent";
export const COOKIE_CONSENT_OPEN_EVENT = "hoocon-cookie-consent-open";

export type CookieConsentState = {
  version: typeof COOKIE_CONSENT_VERSION;
  /** Always true — site operation, CSRF, form protection. Not user-togglable. */
  essential: true;
  /** Optional: Yandex Metrika / GA4 after explicit consent. */
  analytics: boolean;
  updatedAt: string;
};

/**
 * Build a consent snapshot.
 *
 * Args:
 *   analytics: Whether optional analytics cookies are allowed.
 *
 * Returns:
 *   CookieConsentState ready to persist.
 */
export function buildCookieConsent(analytics: boolean): CookieConsentState {
  return {
    version: COOKIE_CONSENT_VERSION,
    essential: true,
    analytics,
    updatedAt: new Date().toISOString(),
  };
}

/**
 * Parse stored consent, including legacy "accepted" / "declined" strings.
 *
 * Args:
 *   raw: localStorage value or null.
 *
 * Returns:
 *   Parsed state, or null if the user has not chosen yet.
 */
export function parseCookieConsent(raw: string | null): CookieConsentState | null {
  if (raw === null || raw === "") {
    return null;
  }
  if (raw === "accepted") {
    return buildCookieConsent(true);
  }
  if (raw === "declined") {
    return buildCookieConsent(false);
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
 *
 * Returns:
 *   Consent state or null when unset / storage unavailable.
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
    return parseCookieConsent(raw);
  } catch {
    return null;
  }
}

/**
 * Persist consent and notify same-tab listeners.
 *
 * Args:
 *   state: Consent to store.
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
 *
 * Args:
 *   state: Current consent or null.
 *
 * Returns:
 *   True only after explicit analytics opt-in.
 */
export function isAnalyticsAllowed(state: CookieConsentState | null): boolean {
  return state?.analytics === true;
}

/** Ask CookieConsent UI to open the preferences panel. */
export function openCookieConsentSettings(): void {
  window.dispatchEvent(new Event(COOKIE_CONSENT_OPEN_EVENT));
}
