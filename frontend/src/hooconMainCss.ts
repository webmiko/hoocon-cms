/** Shared id for Vite entry CSS link (async media=print → all). */
export const HOOCON_MAIN_CSS_ID = "hoocon-main-css";

/** Boot splash in ``index.html`` (mobile only; removed after ready + min dwell). */
export const HOOCON_SPLASH_ID = "hoocon-splash";

/**
 * Show splash only on mobile layout — sync with ``Layout.module.css``
 * ``@media (max-width: 960px)`` and ``index.html`` critical CSS.
 */
export const HOOCON_SPLASH_MOBILE_MQ = "(max-width: 960px)";

/** Minimum splash visibility (ms) to avoid flash on fast starts. */
export const HOOCON_SPLASH_MIN_MS = 3000;

/** Fade-out duration — keep in sync with ``#hoocon-splash`` transition in index.html. */
export const HOOCON_SPLASH_FADE_MS = 400;

/** True when the boot splash should run (phone / narrow viewport). */
export function isSplashViewport(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) {
    return false;
  }
  return window.matchMedia(HOOCON_SPLASH_MOBILE_MQ).matches;
}

/**
 * Extra wait so splash stays at least ``minMs`` from navigation start.
 *
 * Args:
 *   elapsedMs: ``performance.now()`` when content is ready.
 *   minMs: Minimum dwell (default ``HOOCON_SPLASH_MIN_MS``).
 *
 * Returns:
 *   Milliseconds to delay before starting the fade (0 if already past min).
 */
export function splashRemainingDwellMs(
  elapsedMs: number,
  minMs: number = HOOCON_SPLASH_MIN_MS,
): number {
  if (!Number.isFinite(elapsedMs) || elapsedMs < 0) {
    return Math.max(0, minMs);
  }
  return Math.max(0, minMs - elapsedMs);
}
