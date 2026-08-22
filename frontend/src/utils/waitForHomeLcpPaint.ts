import { HOME_LCP_BOOT_ID } from "./adoptHomeSsrLcpImage";

/** Let the LCP entry paint before cookie/adopt work competes on the main thread. */
const LCP_SETTLE_MS = 120;

/** Match ``spa_index`` boot safety timeout when PO / image signals are missing. */
const LCP_FALLBACK_MS = 2800;

/**
 * Resolve after the home LCP hero is likely painted (PSI / Slow 4G).
 *
 * Uses buffered ``largest-contentful-paint``, the SSR boot image ``load``,
 * and a safety timeout. Safe on non-home routes (immediate fallback path).
 */
export function waitForHomeLcpPaint(): Promise<void> {
  if (typeof window === "undefined") {
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    let settled = false;
    let settleTimer: number | undefined;
    let observer: PerformanceObserver | undefined;

    const finish = () => {
      if (settled) {
        return;
      }
      settled = true;
      observer?.disconnect();
      window.clearTimeout(fallbackTimer);
      if (settleTimer !== undefined) {
        window.clearTimeout(settleTimer);
      }
      resolve();
    };

    const scheduleFinish = () => {
      if (settled) {
        return;
      }
      if (settleTimer !== undefined) {
        window.clearTimeout(settleTimer);
      }
      settleTimer = window.setTimeout(finish, LCP_SETTLE_MS);
    };

    if ("PerformanceObserver" in window) {
      try {
        observer = new PerformanceObserver((list) => {
          if (list.getEntries().length > 0) {
            scheduleFinish();
          }
        });
        observer.observe({ type: "largest-contentful-paint", buffered: true });
      } catch {
        observer = undefined;
      }
    }

    const boot = document.getElementById(HOME_LCP_BOOT_ID);
    if (boot instanceof HTMLImageElement) {
      const onBootReady = () => {
        requestAnimationFrame(() => {
          requestAnimationFrame(scheduleFinish);
        });
      };
      if (boot.complete) {
        onBootReady();
      } else {
        boot.addEventListener("load", onBootReady, { once: true });
        boot.addEventListener("error", scheduleFinish, { once: true });
      }
    } else {
      requestAnimationFrame(() => {
        requestAnimationFrame(scheduleFinish);
      });
    }

    const fallbackTimer = window.setTimeout(finish, LCP_FALLBACK_MS);
  });
}
