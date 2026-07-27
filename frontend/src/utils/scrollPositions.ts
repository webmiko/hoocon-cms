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

/**
 * Apply ``scrollTo`` and retry while the document is still growing
 * (async catalog / PDP content). Stops when height can host ``targetY``
 * or after a short deadline.
 *
 * Args:
 *   targetY: Desired scroll offset.
 *   maxMs: How long to keep retrying (default 2s).
 */
export function restoreScrollPosition(targetY: number, maxMs = 2000): () => void {
  const y = Math.max(0, Math.round(targetY));
  let cancelled = false;
  const started = performance.now();

  const apply = () => {
    if (cancelled) return;
    window.scrollTo({ top: y, left: 0, behavior: "auto" });
  };

  apply();

  const tick = () => {
    if (cancelled) return;
    apply();
    const maxY = Math.max(
      0,
      document.documentElement.scrollHeight - window.innerHeight,
    );
    const elapsed = performance.now() - started;
    if (maxY >= y - 1 || elapsed >= maxMs) {
      apply();
      return;
    }
    window.requestAnimationFrame(tick);
  };

  window.requestAnimationFrame(tick);

  return () => {
    cancelled = true;
  };
}
