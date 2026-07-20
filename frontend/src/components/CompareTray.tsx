import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { useCompare } from "../compare/CompareContext";
import {
  COMPARE_MAX_SKUS,
  COMPARE_MIN_FOR_PAGE,
} from "../compare/constants";
import { buildCompareSearch } from "../compare/storage";
import { softBreak } from "../utils/softBreak";
import styles from "./CompareTray.module.css";

/**
 * Fixed bottom bar: selected SKUs + «Перейти к сравнению».
 * Hidden on /compare itself and when the set is empty.
 */
export function CompareTray() {
  const { items, count, remove, clear } = useCompare();
  const location = useLocation();
  const onComparePage = location.pathname === "/compare";
  const prevCount = useRef(count);
  const [pulse, setPulse] = useState(false);

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

  if (onComparePage || count === 0) {
    return null;
  }

  const needMore = count < COMPARE_MIN_FOR_PAGE;
  const compareTo = `/compare${buildCompareSearch(items.map((i) => i.slug))}`;

  return (
    <div
      className={`${styles.tray} ${pulse ? styles.trayPulse : ""}`.trim()}
      role="region"
      aria-label="Сравнение товаров"
      data-compare-tray=""
    >
      <div className={styles.inner}>
        <div className={styles.metaBlock}>
          <p className={styles.meta}>
            В сравнении: {count} из {COMPARE_MAX_SKUS}
          </p>
          {needMore ? (
            <p className={styles.hint} role="status">
              Добавьте ещё модель — или откройте список
            </p>
          ) : null}
        </div>
        <ul className={styles.list}>
          {items.map((item) => (
            <li key={item.slug} className={styles.item}>
              {item.image ? (
                <img
                  src={item.image}
                  alt=""
                  className={styles.thumb}
                  width={40}
                  height={40}
                  loading="lazy"
                  decoding="async"
                />
              ) : (
                <span className={styles.thumbPlaceholder} aria-hidden="true" />
              )}
              <span className={`${styles.code} text-tech`}>
                {softBreak(item.sku_code)}
              </span>
              <button
                type="button"
                className={styles.remove}
                onClick={() => remove(item.slug)}
                aria-label={`Убрать ${item.sku_code} из сравнения`}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
        <div className={styles.actions}>
          <button type="button" className={styles.clear} onClick={clear}>
            Очистить
          </button>
          <Link
            to={compareTo}
            className={`${styles.compare} ${pulse ? styles.comparePulse : ""}`.trim()}
          >
            Перейти к сравнению
          </Link>
        </div>
      </div>
    </div>
  );
}
