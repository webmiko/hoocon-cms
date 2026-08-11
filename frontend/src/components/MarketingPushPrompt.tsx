/**
 * Soft marketing push prompt after cookie marketing consent.
 * Deferred (not on critical LCP path); dismissible for 14 days.
 *
 * Do not treat a support-chat PushSubscription as «already on news» —
 * marketing is a separate topic flag on the same endpoint.
 */

import { useEffect, useId, useRef, useState } from "react";

import {
  COOKIE_CONSENT_CHANGE_EVENT,
  isMarketingAllowed,
  readCookieConsent,
  type CookieConsentState,
} from "../utils/cookieConsent";
import {
  getSupportChatState,
  subscribeSupportChat,
} from "../utils/supportChatControl";
import {
  hasBrowserPushSubscription,
  pushSupported,
  subscribeWebPush,
  subscribeWebPushStatusRu,
} from "../utils/webPush";
import styles from "./MarketingPushPrompt.module.css";

const DISMISS_KEY = "hoocon-marketing-push-dismissed-until";
const DONE_KEY = "hoocon-marketing-push-subscribed";
const DISMISS_MS = 14 * 24 * 60 * 60 * 1000;

function isMarketingPushDone(): boolean {
  try {
    return localStorage.getItem(DONE_KEY) === "1";
  } catch {
    return false;
  }
}

function markMarketingPushDone() {
  try {
    localStorage.setItem(DONE_KEY, "1");
    localStorage.removeItem(DISMISS_KEY);
  } catch {
    /* ignore */
  }
}

function clearMarketingPushDone() {
  try {
    localStorage.removeItem(DONE_KEY);
  } catch {
    /* ignore */
  }
}

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

function clearDismiss() {
  try {
    localStorage.removeItem(DISMISS_KEY);
  } catch {
    /* ignore */
  }
}

/** Done flag is stale if permission/sub/consent was revoked. */
async function refreshMarketingDoneFlag(): Promise<boolean> {
  if (!isMarketingPushDone()) return false;
  if (!isMarketingAllowed(readCookieConsent())) {
    clearMarketingPushDone();
    return false;
  }
  if (typeof Notification !== "undefined" && Notification.permission !== "granted") {
    clearMarketingPushDone();
    return false;
  }
  if (!(await hasBrowserPushSubscription())) {
    clearMarketingPushDone();
    return false;
  }
  return true;
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
  const hideTimerRef = useRef<number | null>(null);
  const marketingWasOnRef = useRef(isMarketingAllowed(readCookieConsent()));

  useEffect(() => {
    let cancelled = false;

    async function canOffer(): Promise<boolean> {
      if (!pushSupported()) return false;
      if (!isMarketingAllowed(readCookieConsent())) return false;
      if (typeof Notification !== "undefined" && Notification.permission === "denied") {
        return false;
      }
      if (await refreshMarketingDoneFlag()) return false;
      if (getSupportChatState().open) return false;
      return true;
    }

    const timer = window.setTimeout(() => {
      void (async () => {
        if (cancelled) return;
        if (!(await canOffer()) || isDismissed()) return;
        if (!cancelled) setVisible(true);
      })();
    }, 4000);

    function onConsent(event: Event) {
      const detail = (event as CustomEvent<CookieConsentState>).detail;
      const marketingOn = isMarketingAllowed(detail);
      const wasOn = marketingWasOnRef.current;
      marketingWasOnRef.current = marketingOn;

      if (!marketingOn) {
        clearMarketingPushDone();
        setVisible(false);
        void import("../utils/webPush").then(({ syncMarketingPushConsent }) =>
          syncMarketingPushConsent(false),
        );
        return;
      }
      if (!pushSupported()) {
        setVisible(false);
        return;
      }
      void (async () => {
        if (await refreshMarketingDoneFlag()) {
          if (!cancelled) setVisible(false);
          return;
        }
        // Only re-offer on fresh marketing opt-in (false → true).
        if (!wasOn && marketingOn) {
          clearDismiss();
          if (!cancelled && !getSupportChatState().open) setVisible(true);
        }
      })();
    }

    const unsubChat = subscribeSupportChat((next) => {
      if (next.open) setVisible(false);
    });

    window.addEventListener(COOKIE_CONSENT_CHANGE_EVENT, onConsent);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      if (hideTimerRef.current != null) window.clearTimeout(hideTimerRef.current);
      window.removeEventListener(COOKIE_CONSENT_CHANGE_EVENT, onConsent);
      unsubChat();
    };
  }, []);

  if (!visible) return null;

  async function enable() {
    setStatus("");
    setBusy(true);
    try {
      if (!isMarketingAllowed(readCookieConsent())) {
        setStatus("Включите «Новости и акции» в настройках cookie");
        return;
      }
      const result = await subscribeWebPush({ topic_marketing: true });
      if (result.ok) {
        setStatus("Готово — будем присылать новости");
        markMarketingPushDone();
        hideTimerRef.current = window.setTimeout(() => setVisible(false), 2000);
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
