import { createContext, useContext } from "react";

import type { ResolvedTheme, ThemePreference } from "../utils/theme";

export type ThemeContextValue = {
  preference: ThemePreference;
  resolved: ResolvedTheme;
  label: string;
  setPreference: (preference: ThemePreference) => void;
  cyclePreference: () => void;
};

export const ThemeContext = createContext<ThemeContextValue | null>(null);

/**
 * Consume theme from ThemeProvider.
 *
 * Returns:
 *   Preference, resolved theme, setters, and a Russian UI label.
 *
 * Raises:
 *   Error if used outside ThemeProvider.
 */
export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return ctx;
}
