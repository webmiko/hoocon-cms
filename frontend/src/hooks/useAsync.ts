import { useEffect, useReducer } from "react";

/**
 * Async data hook for fetching API data in components.
 *
 * Spec: ПЛАН §6 Iter 4; docs/readiness-backend-ux.md.
 *
 * Args:
 *   asyncFn: function returning a Promise<T>.
 *   deps: dependency array (re-fetches when these change).
 *
 * Returns:
 *   { data, loading, error } — standard async state.
 */
export function useAsync<T>(asyncFn: () => Promise<T>, deps: unknown[]): {
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

  useEffect(() => {
    let cancelled = false;
    dispatch({ type: "loading" });
    asyncFn()
      .then((result) => {
        if (!cancelled) dispatch({ type: "success", data: result });
      })
      .catch((err: Error) => {
        if (!cancelled) dispatch({ type: "error", error: err });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
