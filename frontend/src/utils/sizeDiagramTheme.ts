/**
 * Theme-aware URL for technical size diagrams (black line art on transparent).
 *
 * Light theme keeps ``*-size.webp`` (dark strokes). Dark theme swaps to
 * ``*-size-dark.webp`` (white strokes) generated beside the light asset.
 *
 * Manual PDF crops (wiring / dimensions on white paper) are not swapped —
 * they use a white PhotoWash backdrop instead.
 */

import type { ResolvedTheme } from "./theme";

/**
 * True when the media URL is a catalog size/габариты diagram (``*-size`` assets).
 *
 * Args:
 *   src: Absolute or relative image URL.
 *   alt: Optional alt text (``габариты`` marker).
 */
export function isSizeDiagram(src: string, alt?: string): boolean {
  if (/-size(?:-dark)?\./i.test(src)) {
    return true;
  }
  if (alt && alt.toLowerCase().includes("габарит") && /-size/i.test(src)) {
    return true;
  }
  return false;
}

/**
 * True for manual wiring/dimension crops and ``*-size`` line-art diagrams.
 *
 * These tiles should sit on a white (paper) backdrop, not a product photo wash.
 */
export function isTechnicalDiagram(src: string, alt?: string): boolean {
  if (isSizeDiagram(src, alt)) {
    return true;
  }
  if (/-(?:dimensions|wiring|aux[_-]switch|settings)\./i.test(src)) {
    return true;
  }
  if (/montazhnaya_sxema/i.test(src)) {
    return true;
  }
  const label = (alt || "").toLowerCase();
  return (
    label.includes("схема подключения") ||
    label.includes("монтажн") ||
    label.includes("вспомогательн") ||
    label.includes("dip") ||
    label.includes("настройка") ||
    label.includes("габаритные размеры") ||
    label.includes("чертёж") ||
    // Tilda alts: «схема размеров и подключения к сети …»
    (label.includes("схема") &&
      (label.includes("размер") || label.includes("подключ"))) ||
    (label.includes("термодатчик") && label.includes("схема"))
  );
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
  if (!/-size(?:-dark)?\./i.test(src)) {
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
