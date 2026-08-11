/**
 * Soft marketing push prompt after cookie marketing consent.
 * Deferred (not on critical LCP path); dismissible for 14 days.
 */

import { useEffect, useId, useState } from "react";

import {
  COOKIE_CONSENT_CHANGE_EVENT,
  isMarketingAllowed,
  readCookieConsent,
  type CookieConsentState,
} from "../utils/cookieConsent";
import {
  hasBrowserPushSubscription,
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

function BellIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      width="22"
      height="22"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="currentColor"
        d={
          "M12 22a2.2 2.2 0 0 0 2.2-2.2h-4.4A2.2 2.2 0 0 0 12 22Zm7-6.2V11a7 7 0 1 0-14 0v4.8L3 18v1h18v-1l-2-2.2Z"
        }
      />
    </svg>
  );
}

export function MarketingPushPrompt() {
  const titleId = useId();
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void (async () => {
        if (!pushSupported() || isDismissed()) return;
        if (!isMarketingAllowed(readCookieConsent())) return;
        // Already subscribed in this browser — do not nag after reload.
        if (await hasBrowserPushSubscription()) {
          dismiss();
          return;
        }
        if (!cancelled) setVisible(true);
      })();
    }, 4000);

    function onConsent(event: Event) {
      const detail = (event as CustomEvent<CookieConsentState>).detail;
      void (async () => {
        if (!isMarketingAllowed(detail) || !pushSupported() || isDismissed()) {
          setVisible(false);
          return;
        }
        if (await hasBrowserPushSubscription()) {
          dismiss();
          setVisible(false);
          return;
        }
        setVisible(true);
      })();
    }
    window.addEventListener(COOKIE_CONSENT_CHANGE_EVENT, onConsent);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      window.removeEventListener(COOKIE_CONSENT_CHANGE_EVENT, onConsent);
    };
  }, []);

  if (!visible) return null;

  async function enable() {
    setStatus("");
    setBusy(true);
    try {
      const result = await subscribeWebPush({ topic_marketing: true });
      if (result.ok) {
        setStatus("Готово — будем присылать новости");
        dismiss();
        window.setTimeout(() => setVisible(false), 2000);
      } else {
        setStatus(subscribeWebPushStatusRu(result) || "Не удалось включить");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className={styles.banner} aria-labelledby={titleId}>
      <div className={styles.iconWrap} aria-hidden="true">
        <BellIcon className={styles.icon} />
      </div>
      <div className={styles.body}>
        <p id={titleId} className={styles.title}>
          Новости Hoocon в браузере
        </p>
        <p className={styles.text}>
          Включить push о новинках и предложениях? Можно отключить в настройках
          cookie.
        </p>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.primary}
            disabled={busy}
            onClick={() => void enable()}
          >
            {busy ? "Подключаем…" : "Включить"}
          </button>
          <button
            type="button"
            className={styles.secondary}
            disabled={busy}
            onClick={() => {
              dismiss();
              setVisible(false);
            }}
          >
            Не сейчас
          </button>
        </div>
        {status ? <p className={styles.status}>{status}</p> : null}
      </div>
    </aside>
  );
}
