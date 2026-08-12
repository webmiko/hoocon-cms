import { useEffect, useId, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { useCompare } from "../compare/useCompare";
import { COMPARE_MAX_SKUS } from "../compare/constants";
import { buildCompareSearch } from "../compare/storage";
import { ProtectedProductImage } from "./ProtectedProductImage";
import { softBreak } from "../utils/softBreak";
import { protectedContentHandlers } from "../utils/contentProtection";
import { setSupportChatOpen } from "../utils/supportChatControl";
import styles from "./CompareTray.module.css";

function ChatIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d={
          "M4.5 4.75A2.75 2.75 0 0 1 7.25 2h9.5A2.75 2.75 0 0 1 19.5 4.75v8.5A2.75 "
          + "2.75 0 0 1 16.75 16H12.1l-3.72 3.1a.75.75 0 0 1-1.23-.57V16H7.25A2.75 "
          + "2.75 0 0 1 4.5 13.25v-8.5Z"
        }
      />
    </svg>
  );
}

/** Left/right arrows — compare / swap (not pause bars). */
function CompareIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d={
          "M9.01 14H2v2h7.01v3L13 15l-3.99-4v3zm5.98-1v-3H22V8h-7.01V5L11 9l3.99 4z"
        }
      />
    </svg>
  );
}

export type EmptyDockCta =
  | { kind: "to"; to: string; label: string }
  | { kind: "href"; href: string; label: string };

type CompareTrayProps = {
  /** Mobile empty dock (Chat + KP) when sticky CTA would show. */
  showWhenEmpty?: boolean;
  /** KP target for the empty dock (consultation / factory). */
  emptyCta?: EmptyDockCta;
};

/**
 * Bottom dock: Chat (left) + КП (right).
 * With selected SKUs — expands to RFQ tray (summary / compare / clear).
 * Empty dock is mobile-only; selection tray shows on all widths.
 */
export function CompareTray({
  showWhenEmpty = false,
  emptyCta = { kind: "to", to: "/consultation", label: "Запросить КП" },
}: CompareTrayProps) {
  const { items, count, remove, clear } = useCompare();
  const location = useLocation();
  const onComparePage = location.pathname === "/compare";
  const onRfqPage = location.pathname === "/rfq";
  const prevCount = useRef(count);
  const [pulse, setPulse] = useState(false);
  const [open, setOpen] = useState(false);
  const panelId = useId();

  useEffect(() => {
    if (count > prevCount.current && count > 0) {
      setPulse(true);
      const timer = window.setTimeout(() => setPulse(false), 1600);
      prevCount.current = count;
      return () => window.clearTimeout(timer);
    }
    prevCount.current = count;
    return undefined;
  }, [count]);

  const hasSelection = count > 0;
  const hideOnRoute = onComparePage || onRfqPage;
  if (hideOnRoute || (!hasSelection && !showWhenEmpty)) {
    return null;
  }

  const panelOpen = open && hasSelection;
  const slugs = items.map((i) => i.slug);
  const compareTo = `/compare${buildCompareSearch(slugs)}`;
  const rfqTo = `/rfq?skus=${encodeURIComponent(slugs.join(","))}`;
  const preview = items.slice(0, COMPARE_MAX_SKUS);
  const emptyOnly = !hasSelection;

  const kpClass = `${styles.compare} ${pulse ? styles.comparePulse : ""}`.trim();
  const shortKp =
    !hasSelection && emptyCta.kind === "href" ? "OEM" : "КП";
  const kpLabel = (
    <>
      <span className={styles.compareFull}>
        {hasSelection ? "Запросить КП" : emptyCta.label}
      </span>
      <span className={styles.compareShort} aria-hidden="true">
        {shortKp}
      </span>
    </>
  );

  return (
    <div
      className={[
        styles.tray,
        pulse ? styles.trayPulse : "",
        emptyOnly ? styles.trayEmpty : "",
      ]
        .filter(Boolean)
        .join(" ")}
      role="region"
      aria-label={
        hasSelection ? "Выбранные артикулы для КП" : "Быстрые действия"
      }
      data-mobile-dock={panelOpen ? "open" : ""}
      data-dock-mode={emptyOnly ? "empty" : "tray"}
      data-compare-tray={hasSelection ? (panelOpen ? "open" : "") : undefined}
    >
      {panelOpen ? (
        <div
          id={panelId}
          className={`${styles.panel} u-protect-content`}
          {...protectedContentHandlers}
        >
          <div className={styles.panelToolbar}>
            <p className={styles.panelTitle}>Выбрано для КП</p>
            <button type="button" className={styles.panelClear} onClick={clear}>
              Очистить всё
            </button>
          </div>
          <ul className={styles.panelList} role="list">
            {items.map((item) => (
              <li key={item.slug} className={styles.panelItem}>
                {item.image ? (
                  <ProtectedProductImage
                    src={item.image}
                    alt=""
                    frameClassName={styles.panelThumb}
                    className="u-protect-media"
                    compact
                    width={32}
                    height={32}
                    loading="lazy"
                  />
                ) : (
                  <span
                    className={styles.panelThumbPlaceholder}
                    aria-hidden="true"
                  />
                )}
                <span className={`${styles.panelCode} text-tech`}>
                  {softBreak(item.sku_code)}
                </span>
                <button
                  type="button"
                  className={styles.remove}
                  onClick={() => remove(item.slug)}
                  aria-label={`Убрать ${item.sku_code} из списка КП`}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
          <div className={styles.panelLinks}>
            <Link to={compareTo} className={styles.panelCompare}>
              Сравнить модели
            </Link>
          </div>
        </div>
      ) : null}

      <div
        className={`${styles.inner} ${emptyOnly ? styles.innerEmpty : ""}`.trim()}
      >
        <button
          type="button"
          className={styles.chat}
          aria-label="Открыть чат поддержки"
          onClick={() => setSupportChatOpen(true)}
        >
          <ChatIcon className={styles.chatIcon} />
          <span className={styles.chatLabel}>Чат</span>
        </button>

        {hasSelection ? (
          <button
            type="button"
            className={styles.summary}
            aria-expanded={panelOpen}
            aria-controls={panelId}
            aria-label={
              panelOpen
                ? `Скрыть список: ${count} из ${COMPARE_MAX_SKUS}`
                : `Показать список: ${count} из ${COMPARE_MAX_SKUS}`
            }
            onClick={() => setOpen((v) => !v)}
          >
            <span className={styles.stack} aria-hidden="true">
              {preview.map((item, index) => (
                <span
                  key={item.slug}
                  className={styles.stackSlot}
                  style={{ zIndex: preview.length - index }}
                >
                  {item.image ? (
                    <ProtectedProductImage
                      src={item.image}
                      alt=""
                      frameClassName={styles.stackThumb}
                      className="u-protect-media"
                      compact
                      width={28}
                      height={28}
                      loading="lazy"
                    />
                  ) : (
                    <span className={styles.stackPlaceholder} />
                  )}
                </span>
              ))}
            </span>
            <span className={styles.summaryText} aria-hidden="true">
              <span className={styles.summaryCount}>
                {count} из {COMPARE_MAX_SKUS}
              </span>
              <span className={styles.summaryLabel}>
                {panelOpen ? "Скрыть" : "Для КП"}
              </span>
            </span>
            <span
              className={`${styles.chevron} ${panelOpen ? styles.chevronOpen : ""}`.trim()}
              aria-hidden="true"
            />
          </button>
        ) : null}

        <div className={styles.actions}>
          {hasSelection ? (
            <>
              <button type="button" className={styles.clear} onClick={clear}>
                Очистить
              </button>
              <Link
                to={compareTo}
                className={styles.secondary}
                aria-label="Сравнить модели"
              >
                <CompareIcon className={styles.secondaryIcon} />
                <span className={styles.secondaryLabel}>Сравнить</span>
              </Link>
              <Link to={rfqTo} className={kpClass} aria-label="Запросить КП">
                {kpLabel}
              </Link>
            </>
          ) : emptyCta.kind === "href" ? (
            <a
              href={emptyCta.href}
              className={kpClass}
              aria-label={emptyCta.label}
            >
              {kpLabel}
            </a>
          ) : (
            <Link
              to={emptyCta.to}
              className={kpClass}
              aria-label={emptyCta.label}
            >
              {kpLabel}
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
