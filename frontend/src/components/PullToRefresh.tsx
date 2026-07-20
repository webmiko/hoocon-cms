import type { ReactNode } from "react";

import {
  usePullToRefresh,
  type UsePullToRefreshOptions,
} from "../hooks/usePullToRefresh";
import styles from "./PullToRefresh.module.css";

type PullToRefreshProps = UsePullToRefreshOptions & {
  children: ReactNode;
};

/**
 * Wraps the SPA with a tactile pull-to-refresh gesture and brand spinner.
 */
export function PullToRefresh({
  children,
  onRefresh,
  disabled = false,
}: PullToRefreshProps) {
  const { status, pullDistance, progress } = usePullToRefresh({
    onRefresh,
    disabled,
  });

  const active = status === "pulling" || status === "armed" || status === "refreshing";
  const spinnerVisible = pullDistance > 8 || status === "refreshing";
  const rotationDeg = status === "refreshing" ? 0 : progress * 270;

  return (
    <>
      <div
        className={
          status === "refreshing"
            ? `${styles.indicator} ${styles.indicatorRefreshing}`
            : styles.indicator
        }
        style={{ height: `${pullDistance}px` }}
        aria-hidden={status === "idle"}
        role="status"
        aria-live="polite"
        aria-label={
          status === "refreshing"
            ? "Обновление страницы"
            : status === "armed"
              ? "Отпустите для обновления"
              : undefined
        }
      >
        <div
          className={
            spinnerVisible
              ? `${styles.spinnerWrap} ${styles.spinnerWrapVisible}`
              : styles.spinnerWrap
          }
        >
          <div
            className={
              status === "refreshing"
                ? `${styles.spinner} ${styles.spinnerSpinning}`
                : styles.spinner
            }
            style={
              status === "refreshing"
                ? undefined
                : { transform: `rotate(${rotationDeg}deg)` }
            }
          />
        </div>
      </div>

      <div
        className={active ? `${styles.content} ${styles.contentActive}` : styles.content}
        style={{ transform: `translateY(${pullDistance}px)` }}
      >
        {children}
      </div>
    </>
  );
}
