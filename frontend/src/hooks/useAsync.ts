import { useEffect, useEffectEvent, useReducer } from "react";

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
 *
 * Returns:
 *   { data, loading, error } — standard async state.
 */
export function useAsync<T>(
  asyncFn: () => Promise<T>,
  refreshKey: AsyncRefreshKey = 0,
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
    { data: undefined, loading: true, error: undefined },
  );

  const load = useEffectEvent(asyncFn);

  useEffect(() => {
    let cancelled = false;
    dispatch({ type: "loading" });
    void load()
      .then((result) => {
        if (!cancelled) dispatch({ type: "success", data: result });
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
  }, [refreshKey]);

  return state;
}
