/**
 * In-memory scroll positions keyed by React Router ``location.key``.
 * Spec: SPA back-navigation restore (catalog → PDP → back).
 */

const positions = new Map<string, number>();

/**
 * Remember window scroll for a history entry.
 *
 * Args:
 *   key: ``location.key`` from React Router.
 *   y: ``window.scrollY`` (or equivalent).
 */
export function rememberScrollPosition(key: string, y: number): void {
  if (!key) return;
  positions.set(key, Math.max(0, Math.round(y)));
}

/**
 * Read a previously saved scroll position.
 *
 * Args:
 *   key: ``location.key``.
 *
 * Returns:
 *   Saved Y or ``undefined`` when unknown.
 */
export function readScrollPosition(key: string): number | undefined {
  if (!key) return undefined;
  return positions.get(key);
}

type RestoreOptions = {
  maxMs?: number;
  /** Stop only after scrollHeight stayed unchanged this many frames. */
  stableFrames?: number;
};

function watchUntilStable(
  apply: () => void,
  options: RestoreOptions,
): () => void {
  const maxMs = options.maxMs ?? 4000;
  const needStable = options.stableFrames ?? 10;
  let cancelled = false;
  const started = performance.now();
  let lastHeight = -1;
  let stable = 0;

  const tick = () => {
    if (cancelled) return;
    apply();
    const height = document.documentElement.scrollHeight;
    if (height === lastHeight) {
      stable += 1;
    } else {
      lastHeight = height;
      stable = 0;
    }
    const elapsed = performance.now() - started;
    if (stable >= needStable || elapsed >= maxMs) {
      apply();
      return;
    }
    window.requestAnimationFrame(tick);
  };

  apply();
  window.requestAnimationFrame(tick);

  return () => {
    cancelled = true;
  };
}

/**
 * Apply ``scrollTo`` and keep correcting while layout/images change height.
 *
 * Args:
 *   targetY: Desired scroll offset.
 *   maxMs: How long to keep retrying (default 4s).
 */
export function restoreScrollPosition(targetY: number, maxMs = 4000): () => void {
  const y = Math.max(0, Math.round(targetY));
  return watchUntilStable(
    () => {
      window.scrollTo({ top: y, left: 0, behavior: "auto" });
    },
    { maxMs, stableFrames: 10 },
  );
}

/**
 * Keep an element centered in the viewport while images/layout settle.
 *
 * Args:
 *   el: Catalog card (or any anchor) to bring into view.
 *   maxMs: Retry budget.
 */
export function restoreScrollToElement(
  el: HTMLElement,
  maxMs = 4000,
): () => void {
  return watchUntilStable(
    () => {
      el.scrollIntoView({ block: "center", behavior: "auto" });
    },
    { maxMs, stableFrames: 12 },
  );
}
