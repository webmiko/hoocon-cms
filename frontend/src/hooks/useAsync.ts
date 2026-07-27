import { useEffect, useEffectEvent, useReducer } from "react";

import { peekAsyncCache, setAsyncCache } from "../utils/asyncDataCache";

/** Primitive key that triggers a refetch when it changes (Object.is). */
export type AsyncRefreshKey = string | number | boolean | null | undefined;

/**
 * Async data hook for fetching API data in components.
 *
 * Spec: план Iter 4; docs/readiness-backend-ux.md.
 *
 * Args:
 *   asyncFn: function returning a Promise<T> (latest via useEffectEvent).
 *   refreshKey: change to re-fetch (compose multi-deps with a string).
 *   cacheKey: optional session cache key — remounts reuse last success so
 *     catalog/PDP do not flash an empty skeleton on back-navigation.
 *
 * Returns:
 *   { data, loading, error } — standard async state.
 */
export function useAsync<T>(
  asyncFn: () => Promise<T>,
  refreshKey: AsyncRefreshKey = 0,
  cacheKey?: string,
): {
  data: T | undefined;
  loading: boolean;
  error: Error | undefined;
} {
  const [state, dispatch] = useReducer(
    (
      prev: { data: T | undefined; loading: boolean; error: Error | undefined },
      action:
        | { type: "loading" }
        | { type: "success"; data: T }
        | { type: "error"; error: Error },
    ) => {
      switch (action.type) {
        case "loading":
          return { data: prev.data, loading: true, error: undefined };
        case "success":
          return { data: action.data, loading: false, error: undefined };
        case "error":
          return { data: prev.data, loading: false, error: action.error };
      }
    },
    undefined,
    () => {
      const cached = cacheKey ? peekAsyncCache<T>(cacheKey) : undefined;
      return {
        data: cached,
        loading: cached === undefined,
        error: undefined,
      };
    },
  );

  const load = useEffectEvent(asyncFn);

  useEffect(() => {
    let cancelled = false;
    const cached = cacheKey ? peekAsyncCache<T>(cacheKey) : undefined;
    // Keep painted data on remount; only show loading when nothing to show.
    if (cached === undefined) {
      dispatch({ type: "loading" });
    }
    void load()
      .then((result) => {
        if (cancelled) return;
        if (cacheKey) {
          setAsyncCache(cacheKey, result);
        }
        dispatch({ type: "success", data: result });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          dispatch({
            type: "error",
            error: err instanceof Error ? err : new Error(String(err)),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey, cacheKey]);

  return state;
}
