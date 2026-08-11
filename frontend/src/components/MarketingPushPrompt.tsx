/**
 * Soft marketing push prompt after cookie marketing consent.
 * Deferred (not on critical LCP path); dismissible for 14 days.
 */

import { useEffect, useState } from "react";

import {
  COOKIE_CONSENT_CHANGE_EVENT,
  isMarketingAllowed,
  readCookieConsent,
  type CookieConsentState,
} from "../utils/cookieConsent";
import {
  pushSupported,
  subscribeWebPush,
  subscribeWebPushStatusRu,
} from "../utils/webPush";
import styles from "./MarketingPushPrompt.module.css";

const DISMISS_KEY = "hoocon-marketing-push-dismissed-until";
const DISMISS_MS = 14 * 24 * 60 * 60 * 1000;

function isDismissed(): boolean {
  try {
    const raw = localStorage.getItem(DISMISS_KEY);
    if (!raw) return false;
    return Date.now() < Number(raw);
  } catch {
    return false;
  }
}

function dismiss() {
  try {
    localStorage.setItem(DISMISS_KEY, String(Date.now() + DISMISS_MS));
  } catch {
    /* ignore */
  }
}

export function MarketingPushPrompt() {
  const [visible, setVisible] = useState(false);
  const [status, setStatus] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (!pushSupported() || isDismissed()) return;
      if (!isMarketingAllowed(readCookieConsent())) return;
      setVisible(true);
    }, 4000);

    function onConsent(event: Event) {
      const detail = (event as CustomEvent<CookieConsentState>).detail;
      if (isMarketingAllowed(detail) && pushSupported() && !isDismissed()) {
        setVisible(true);
      } else if (!isMarketingAllowed(detail)) {
        setVisible(false);
      }
    }
    window.addEventListener(COOKIE_CONSENT_CHANGE_EVENT, onConsent);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener(COOKIE_CONSENT_CHANGE_EVENT, onConsent);
    };
  }, []);

  if (!visible) return null;

  async function enable() {
    setStatus("");
    const result = await subscribeWebPush({ topic_marketing: true });
    if (result.ok) {
      setStatus("Готово — будем присылать новости");
      dismiss();
      window.setTimeout(() => setVisible(false), 2000);
    } else {
      setStatus(subscribeWebPushStatusRu(result) || "Не удалось включить");
    }
  }

  return (
    <aside className={styles.banner} aria-label="Уведомления о новостях">
      <p className={styles.text}>
        Включить уведомления о новостях и предложениях Hoocon?
      </p>
      <div className={styles.actions}>
        <button type="button" className={styles.primary} onClick={() => void enable()}>
          Включить
        </button>
        <button
          type="button"
          className={styles.secondary}
          onClick={() => {
            dismiss();
            setVisible(false);
          }}
        >
          Не сейчас
        </button>
      </div>
      {status ? <p className={styles.status}>{status}</p> : null}
    </aside>
  );
}
