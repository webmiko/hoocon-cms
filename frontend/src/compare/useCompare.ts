import { useContext } from "react";

import {
  CompareContext,
  type CompareContextValue,
} from "./compareContextBase";

/**
 * Access compare tray state. Must be under CompareProvider.
 */
export function useCompare(): CompareContextValue {
  const ctx = useContext(CompareContext);
  if (!ctx) {
    throw new Error("useCompare must be used within CompareProvider");
  }
  return ctx;
}
