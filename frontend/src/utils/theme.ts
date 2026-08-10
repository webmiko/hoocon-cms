/**
 * Site color theme: light / dark / follow OS (system).
 *
 * Preference lives in localStorage; resolved theme is applied as
 * `document.documentElement.dataset.theme` (CSS: html[data-theme="dark"]).
 * A matching FOUC boot script lives in index.html.
 */

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "hoocon-theme";
export const THEME_CHANGE_EVENT = "hoocon-theme";

const PREFERENCES: readonly ThemePreference[] = ["system", "light", "dark"];

/**
 * Parse a stored preference; unknown values fall back to system.
 *
 * Args:
 *   raw: Value from localStorage or null.
 *
 * Returns:
 *   Valid ThemePreference.
 */
export function parseThemePreference(raw: string | null): ThemePreference {
  if (raw === "light" || raw === "dark" || raw === "system") {
    return raw;
  }
  return "system";
}

/**
 * Resolve preference against the OS color scheme.
 *
 * Args:
 *   preference: User choice (light / dark / system).
 *   systemDark: Whether prefers-color-scheme: dark matches.
 *
 * Returns:
 *   Concrete light or dark theme.
 */
export function resolveTheme(
  preference: ThemePreference,
  systemDark: boolean,
): ResolvedTheme {
  if (preference === "light") {
    return "light";
  }
  if (preference === "dark") {
    return "dark";
  }
  return systemDark ? "dark" : "light";
}

/**
 * Next preference in the cycle: system → light → dark → system.
 *
 * Args:
 *   current: Current preference.
 *
 * Returns:
 *   Next preference.
 */
export function nextThemePreference(current: ThemePreference): ThemePreference {
  const index = PREFERENCES.indexOf(current);
  const safeIndex = index < 0 ? 0 : index;
  return PREFERENCES[(safeIndex + 1) % PREFERENCES.length] ?? "system";
}

/**
 * Read preference from localStorage (system if missing / unavailable).
 *
 * Returns:
 *   Stored ThemePreference.
 */
export function readStoredThemePreference(): ThemePreference {
  try {
    return parseThemePreference(localStorage.getItem(THEME_STORAGE_KEY));
  } catch {
    return "system";
  }
}

/**
 * Persist preference to localStorage.
 *
 * Args:
 *   preference: Value to store.
 */
export function writeStoredThemePreference(preference: ThemePreference): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Ignore write failures (private mode / quota).
  }
}

/**
 * Whether the OS currently prefers a dark color scheme.
 *
 * Returns:
 *   True when prefers-color-scheme: dark matches.
 */
export function getSystemPrefersDark(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) {
    return false;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/**
 * Apply resolved theme to <html> for CSS tokens and native controls.
 *
 * Args:
 *   resolved: Concrete light/dark.
 *   preference: Stored user choice (for UI / debugging).
 */
export function applyThemeToDocument(
  resolved: ResolvedTheme,
  preference: ThemePreference,
): void {
  const root = document.documentElement;
  root.dataset.theme = resolved;
  root.dataset.themePreference = preference;
  root.style.colorScheme = resolved;
}

/**
 * Russian aria / tooltip label for the current preference.
 *
 * Args:
 *   preference: User choice.
 *
 * Returns:
 *   Short label for the theme toggle.
 */
export function themePreferenceLabel(preference: ThemePreference): string {
  if (preference === "light") {
    return "Тема: светлая";
  }
  if (preference === "dark") {
    return "Тема: тёмная";
  }
  return "Тема: как в системе";
}
