/**
 * In-memory stale-while-revalidate cache for ``useAsync`` remounts.
 * Spec: avoid catalog/PDP skeleton flash on SPA back-navigation.
 */

const store = new Map<string, unknown>();

/**
 * Read a cached value without network.
 */
export function peekAsyncCache<T>(key: string): T | undefined {
  if (!key) return undefined;
  return store.get(key) as T | undefined;
}

/**
 * Store a successful fetch for later remounts in this tab session.
 */
export function setAsyncCache<T>(key: string, value: T): void {
  if (!key) return;
  store.set(key, value);
}

/** Test helper. */
export function clearAsyncCacheForTests(): void {
  store.clear();
}
