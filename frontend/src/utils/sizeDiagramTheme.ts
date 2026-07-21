/**
 * Theme-aware URL for technical size diagrams (black line art on transparent).
 *
 * Light theme keeps ``*-size.webp`` (dark strokes). Dark theme swaps to
 * ``*-size-dark.webp`` (white strokes) generated beside the light asset.
 */

import type { ResolvedTheme } from "./theme";

/**
 * True when the media URL is a catalog size/габариты diagram.
 *
 * Args:
 *   src: Absolute or relative image URL.
 *   alt: Optional alt text (``габариты`` marker).
 */
export function isSizeDiagram(src: string, alt?: string): boolean {
  if (alt && alt.toLowerCase().includes("габарит")) {
    return true;
  }
  return /-size(?:-dark)?\./i.test(src);
}

/**
 * Pick light or dark stroke diagram URL for the resolved theme.
 *
 * Args:
 *   src: Image URL (may already be ``-size`` or ``-size-dark``).
 *   resolved: Active resolved theme from ThemeProvider.
 *
 * Returns:
 *   URL with the stroke color matching the theme wash.
 */
export function sizeDiagramSrcForTheme(
  src: string,
  resolved: ResolvedTheme,
): string {
  if (!isSizeDiagram(src)) {
    return src;
  }
  if (resolved === "dark") {
    return src.includes("-size-dark.")
      ? src
      : src.replace(/-size\./i, "-size-dark.");
  }
  return src.includes("-size-dark.")
    ? src.replace(/-size-dark\./i, "-size.")
    : src;
}
