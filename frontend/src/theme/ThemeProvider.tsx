import { useEffect, useState, type ReactNode } from "react";

import {
  applyThemeToDocument,
  getSystemPrefersDark,
  nextThemePreference,
  readStoredThemePreference,
  resolveTheme,
  themePreferenceLabel,
  type ThemePreference,
  writeStoredThemePreference,
} from "../utils/theme";
import { ThemeContext, type ThemeContextValue } from "./ThemeContext";

/**
 * Provides theme preference + resolved light/dark for the app shell.
 * Syncs localStorage, documentElement.dataset.theme, and OS scheme changes.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(() =>
    readStoredThemePreference(),
  );
  const [systemDark, setSystemDark] = useState(() => getSystemPrefersDark());

  const resolved = resolveTheme(preference, systemDark);

  useEffect(() => {
    applyThemeToDocument(resolved, preference);
  }, [resolved, preference]);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) {
      return;
    }
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (event: MediaQueryListEvent) => {
      setSystemDark(event.matches);
    };
    media.addEventListener("change", onChange);
    return () => {
      media.removeEventListener("change", onChange);
    };
  }, []);

  function setPreference(next: ThemePreference) {
    writeStoredThemePreference(next);
    setPreferenceState(next);
  }

  function cyclePreference() {
    setPreferenceState((current) => {
      const next = nextThemePreference(current);
      writeStoredThemePreference(next);
      return next;
    });
  }

  const value: ThemeContextValue = {
    preference,
    resolved,
    label: themePreferenceLabel(preference),
    setPreference,
    cyclePreference,
  };

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
