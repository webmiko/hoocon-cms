import { useState } from "react";
import { Link } from "react-router-dom";

import { useCompare } from "../compare/CompareContext";
import { COMPARE_MAX_SKUS } from "../compare/constants";
import {
  buildCompareSearch,
  type CompareItem,
} from "../compare/storage";
import styles from "./CompareToggle.module.css";

interface CompareToggleProps {
  item: CompareItem;
  /** Visual variant: checkbox on card media vs text button on PDP. */
  variant?: "checkbox" | "button";
  className?: string;
}

/**
 * Add/remove SKU from compare set (max 4).
 */
export function CompareToggle({
  item,
  variant = "checkbox",
  className,
}: CompareToggleProps) {
  const { items, isInCompare, toggle } = useCompare();
  const [limitMsg, setLimitMsg] = useState(false);
  const checked = isInCompare(item.slug);
  const compareHref = `/compare${buildCompareSearch(
    checked
      ? items.map((row) => row.slug)
      : [...items.map((row) => row.slug), item.slug].slice(0, COMPARE_MAX_SKUS),
  )}`;

  function handleChange() {
    const result = toggle(item);
    if (result === "limit") {
      setLimitMsg(true);
      window.setTimeout(() => setLimitMsg(false), 2500);
      return;
    }
    setLimitMsg(false);
  }

  if (variant === "button") {
    return (
      <div className={`${styles.buttonGroup} ${className ?? ""}`.trim()}>
        <button
          type="button"
          className={checked ? styles.buttonActive : styles.button}
          onClick={handleChange}
          aria-pressed={checked}
        >
          {checked ? "В сравнении" : "Сравнить"}
        </button>
        {checked ? (
          <Link to={compareHref} className={styles.goLink}>
            Перейти к сравнению
          </Link>
        ) : null}
        {limitMsg ? (
          <p className={styles.limit} role="status">
            Не больше {COMPARE_MAX_SKUS} моделей
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <label
      className={`${styles.checkboxWrap} ${className ?? ""}`.trim()}
      title={
        checked
          ? "Убрать из сравнения"
          : `Добавить к сравнению (до ${COMPARE_MAX_SKUS})`
      }
    >
      <input
        type="checkbox"
        className={styles.checkbox}
        checked={checked}
        onChange={handleChange}
        aria-label={
          checked
            ? `Убрать ${item.sku_code} из сравнения`
            : `Добавить ${item.sku_code} к сравнению`
        }
      />
      <span className={styles.checkboxUi} aria-hidden="true" />
      {limitMsg ? (
        <span className={styles.limitFloat} role="status">
          Макс. {COMPARE_MAX_SKUS}
        </span>
      ) : null}
    </label>
  );
}
