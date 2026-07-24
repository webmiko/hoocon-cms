/**
 * Pick ТТХ rows for catalog cards: unified primary facet set only.
 *
 * Damper actuators (example ``da3fu230-ds``):
 * moment → voltage → control → [Y/U if modulating] → area → aux_switch
 *
 * Extra rows (runtime / weight / IP) stay on PDP hero, not cards.
 */

export type CardHighlight = {
  key: string;
  name: string;
  value: string;
  unit?: string;
};

/** Max rows on a catalog card (primary set + Y/U). */
export const CARD_HIGHLIGHT_MAX = 7;

/** Fixed card order — same keys for every actuator card when present. */
export const CARD_HIGHLIGHT_ORDER = [
  "moment",
  "voltage",
  "control",
  "control_signal",
  "feedback_signal",
  "area",
  "aux_switch",
  "dn",
  "ways",
  "kvs",
  "material",
] as const;

/**
 * Cap highlights for catalog cards to the unified primary set.
 *
 * Args:
 *   highlights: Ordered rows from the list API.
 *   max: Max rows to show (default {@link CARD_HIGHLIGHT_MAX}).
 *
 * Returns:
 *   Primary-facet subset in {@link CARD_HIGHLIGHT_ORDER}.
 */
export function cardHighlights(
  highlights: CardHighlight[] | undefined,
  max: number = CARD_HIGHLIGHT_MAX,
): CardHighlight[] {
  if (!highlights?.length) return [];
  const byKey = new Map(highlights.map((h) => [h.key, h]));
  const ordered: CardHighlight[] = [];
  for (const key of CARD_HIGHLIGHT_ORDER) {
    const row = byKey.get(key);
    if (row) ordered.push(row);
    if (ordered.length >= max) break;
  }
  return ordered;
}

/**
 * Card ТТХ label: shorten «Управляющий …» so the value stays one line.
 *
 * Catalog cards give width priority to the value column; the full Belimo
 * label does not fit beside long Y-signal strings. PDP keeps the full name.
 *
 * Args:
 *   name: Full highlight label from the API.
 *
 * Returns:
 *   Compact label (``Упр. сигнал Y``) or the original name.
 */
export function compactCardSpecName(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return trimmed;
  return trimmed.replace(/^Управляющий(?=\s)/u, "Упр.");
}
