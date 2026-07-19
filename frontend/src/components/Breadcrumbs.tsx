import { Link } from "react-router-dom";

import { softBreak } from "../utils/softBreak";
import styles from "./Breadcrumbs.module.css";

export interface BreadcrumbItem {
  /** Visible label. */
  label: string;
  /** Link target; omit for the current page. */
  to?: string;
  /** Apply monospace tech style (SKU codes). */
  tech?: boolean;
}

interface BreadcrumbsProps {
  items: BreadcrumbItem[];
}

/**
 * Shared breadcrumb trail for catalog / content / CMS pages.
 *
 * Home (`/`) itself has no trail. Spec: docs/seo-meta-yandex-google.md.
 */
export function Breadcrumbs({ items }: BreadcrumbsProps) {
  if (items.length === 0) return null;

  return (
    <nav className={styles.breadcrumbs} aria-label="Навигационная цепочка">
      <ol className={styles.list}>
        {items.map((item, index) => {
          const isLast = index === items.length - 1;
          const label = softBreak(item.label);
          return (
            <li key={`${item.label}-${item.to ?? "current"}`} className={styles.item}>
              {index > 0 ? (
                <span className={styles.sep} aria-hidden="true">
                  /
                </span>
              ) : null}
              {item.to && !isLast ? (
                <Link to={item.to} className={styles.link}>
                  {label}
                </Link>
              ) : (
                <span
                  className={
                    item.tech
                      ? `${styles.current} text-tech`
                      : styles.current
                  }
                  aria-current={isLast ? "page" : undefined}
                >
                  {label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
