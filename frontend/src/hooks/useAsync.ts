import { useEffect, useEffectEvent, useState } from "react";

import { peekAsyncCache, setAsyncCache } from "../utils/asyncDataCache";

/** Primitive key that triggers a refetch when it changes (Object.is). */
export type AsyncRefreshKey = string | number | boolean | null | undefined;

interface AsyncState<T> {
  key: string;
  data: T | undefined;
  loading: boolean;
  error: Error | undefined;
}

function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

function freshState<T>(key: string, cacheKey?: string): AsyncState<T> {
  const cached = cacheKey ? peekAsyncCache<T>(cacheKey) : undefined;
  return { key, data: cached, loading: cached === undefined, error: undefined };
}

/**
 * Async data hook for fetching API data in components.
 *
 * Spec: план Iter 4; docs/readiness-backend-ux.md.
 *
 * Args:
 *   asyncFn: function returning a Promise<T> (latest via useEffectEvent).
 *     Receives an AbortSignal to cancel in-flight fetches on unmount / refresh.
 *   refreshKey: change to re-fetch (compose multi-deps with a string).
 *   cacheKey: optional session cache key — remounts reuse last success so
 *     catalog/PDP do not flash an empty skeleton on back-navigation.
 *
 * Returns:
 *   { data, loading, error } — always for the *current* key: data of a
 *   previous key is never returned (no stale card / canonical on A→B).
 */
export function useAsync<T>(
  asyncFn: (signal?: AbortSignal) => Promise<T>,
  refreshKey: AsyncRefreshKey = 0,
  cacheKey?: string,
): {
  data: T | undefined;
  loading: boolean;
  error: Error | undefined;
} {
  const key = `${String(refreshKey)}\u0000${cacheKey ?? ""}`;
  const [stored, setStored] = useState<AsyncState<T>>(() => freshState<T>(key, cacheKey));
  let state = stored;
  if (stored.key !== key) {
    // Reset during render: the old key's data must not paint even once.
    state = freshState<T>(key, cacheKey);
    setStored(state);
  }

  const load = useEffectEvent(asyncFn);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    void load(controller.signal)
      .then((result) => {
        if (cancelled) return;
        if (cacheKey) {
          setAsyncCache(cacheKey, result);
        }
        setStored({ key, data: result, loading: false, error: undefined });
      })
      .catch((err: unknown) => {
        if (cancelled || isAbortError(err)) return;
        setStored((prev) => ({
          key,
          data: prev.key === key ? prev.data : undefined,
          loading: false,
          error: err instanceof Error ? err : new Error(String(err)),
        }));
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [key, cacheKey]);

  return { data: state.data, loading: state.loading, error: state.error };
}
