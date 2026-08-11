/**
 * Cookie consent banner + preferences (essential vs analytics vs marketing).
 *
 * Spec: ПЛАН §6 Iter 4 — F10; docs/security-baseline.md §privacy; БЗ §8.6.
 */

import { useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";

import {
  buildCookieConsent,
  COOKIE_CONSENT_OPEN_EVENT,
  isAnalyticsAllowed,
  isMarketingAllowed,
  readCookieConsent,
  writeCookieConsent,
  type CookieConsentState,
} from "../utils/cookieConsent";
import styles from "./CookieConsent.module.css";

const COOKIE_OPEN_CLASS = "cookie-banner-open";

type PanelMode = "banner" | "settings" | "hidden";

function initialMode(): PanelMode {
  return readCookieConsent() === null ? "banner" : "hidden";
}

/**
 * First-visit banner and reopenable settings for cookie categories.
 */
export function CookieConsent() {
  const [mode, setMode] = useState<PanelMode>(initialMode);
  const [analyticsDraft, setAnalyticsDraft] = useState(() =>
    isAnalyticsAllowed(readCookieConsent()),
  );
  const [marketingDraft, setMarketingDraft] = useState(() =>
    isMarketingAllowed(readCookieConsent()),
  );
  const settingsTitleId = useId();

  useEffect(() => {
    function onOpen() {
      const current = readCookieConsent();
      setAnalyticsDraft(isAnalyticsAllowed(current));
      setMarketingDraft(isMarketingAllowed(current));
      setMode("settings");
    }
    window.addEventListener(COOKIE_CONSENT_OPEN_EVENT, onOpen);
    return () => {
      window.removeEventListener(COOKIE_CONSENT_OPEN_EVENT, onOpen);
    };
  }, []);

  useEffect(() => {
    if (mode !== "settings") {
      return;
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && readCookieConsent() !== null) {
        setMode("hidden");
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [mode]);

  useEffect(() => {
    const root = document.documentElement;
    const open = mode !== "hidden";
    if (open) {
      root.classList.add(COOKIE_OPEN_CLASS);
    } else {
      root.classList.remove(COOKIE_OPEN_CLASS);
    }
    return () => {
      root.classList.remove(COOKIE_OPEN_CLASS);
    };
  }, [mode]);

  function persist(analytics: boolean, marketing: boolean) {
    const state: CookieConsentState = buildCookieConsent(analytics, marketing);
    writeCookieConsent(state);
    setAnalyticsDraft(analytics);
    setMarketingDraft(marketing);
    setMode("hidden");
  }

  if (mode === "hidden") {
    return null;
  }

  if (mode === "settings") {
    return (
      <div
        className={styles.panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={settingsTitleId}
      >
        <div className={styles.panelInner}>
          <h2 id={settingsTitleId} className={styles.panelTitle}>
            Настройки cookie
          </h2>
          <p className={styles.panelLead}>
            Обязательные cookie нужны для работы сайта и защиты форм.
            Аналитику и новости включаем только после вашего согласия.
          </p>

          <ul className={styles.categoryList}>
            <li className={styles.category}>
              <div className={styles.categoryHead}>
                <span className={styles.categoryName}>Обязательные</span>
                <span className={styles.categoryBadge}>Всегда включены</span>
              </div>
              <p className={styles.categoryDesc}>
                Сессия, CSRF, согласие на cookie, базовая безопасность форм
                заявок.
              </p>
              <label className={styles.switchRow}>
                <input type="checkbox" checked disabled readOnly />
                <span>Необходимы для сайта</span>
              </label>
            </li>
            <li className={styles.category}>
              <div className={styles.categoryHead}>
                <span className={styles.categoryName}>Аналитика</span>
                <span className={styles.categoryBadgeOptional}>Необязательные</span>
              </div>
              <p className={styles.categoryDesc}>
                Яндекс.Метрика и Google Analytics — статистика посещений, без
                рекламных профилей на стороне сайта.
              </p>
              <label className={styles.switchRow}>
                <input
                  type="checkbox"
                  checked={analyticsDraft}
                  onChange={(event) => setAnalyticsDraft(event.target.checked)}
                />
                <span>Разрешить аналитические cookie</span>
              </label>
            </li>
            <li className={styles.category}>
              <div className={styles.categoryHead}>
                <span className={styles.categoryName}>Новости и акции</span>
                <span className={styles.categoryBadgeOptional}>Необязательные</span>
              </div>
              <p className={styles.categoryDesc}>
                Push-уведомления о новостях и предложениях Hoocon в браузере
                (PWA). Можно отключить в любой момент.
              </p>
              <label className={styles.switchRow}>
                <input
                  type="checkbox"
                  checked={marketingDraft}
                  onChange={(event) => setMarketingDraft(event.target.checked)}
                />
                <span>Разрешить маркетинговые уведомления</span>
              </label>
            </li>
          </ul>

          <p className={styles.panelNote}>
            Подробности — в{" "}
            <Link to="/privacy-policy" className={styles.link}>
              политике конфиденциальности
            </Link>
            .
          </p>

          <div className={styles.actions}>
            <button
              type="button"
              className={styles.acceptButton}
              onClick={() => persist(analyticsDraft, marketingDraft)}
            >
              Сохранить
            </button>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => persist(true, true)}
            >
              Принять все
            </button>
            <button
              type="button"
              className={styles.declineButton}
              onClick={() => persist(false, false)}
            >
              Только обязательные
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={styles.banner}
      role="dialog"
      aria-label="Согласие на использование cookie"
    >
      <div className={styles.content}>
        <p className={styles.text}>
          Используем обязательные cookie для работы сайта и защиты форм.
          Аналитику и новости — только с вашего согласия. Подробности — в
          {" "}
          <Link to="/privacy-policy" className={styles.link}>
            политике конфиденциальности
          </Link>
          .
        </p>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.acceptButton}
            onClick={() => persist(true, true)}
          >
            Принять все
          </button>
          <button
            type="button"
            className={styles.declineButton}
            onClick={() => persist(false, false)}
          >
            Только обязательные
          </button>
          <button
            type="button"
            className={styles.settingsButton}
            onClick={() => setMode("settings")}
          >
            Настроить
          </button>
        </div>
      </div>
    </div>
  );
}
