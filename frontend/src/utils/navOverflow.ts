/** Gap between desktop nav items (matches Layout `--space-lg`). */
export const NAV_GAP_PX = 28;

export type NavItem = {
  to: string;
  label: string;
};

export const DESKTOP_NAV_ITEMS: readonly NavItem[] = [
  { to: "/catalog", label: "Каталог" },
  { to: "/statyi", label: "Статьи" },
  { to: "/novosti", label: "Новости" },
  { to: "/company", label: "О компании" },
  { to: "/zavod", label: "Завод · OEM" },
  { to: "/gde-kupit", label: "Где купить" },
  { to: "/kontakty", label: "Контакты" },
];

/**
 * How many leading nav items fit in one row, reserving space for «Ещё».
 *
 * Args:
 *   available: Nav container inner width in px.
 *   itemWidths: Measured widths of each nav link (same order as items).
 *   moreWidth: Measured width of the «Ещё» control.
 *
 * Returns:
 *   Count of items to show inline (rest go into overflow).
 */
export function countVisibleNavItems(
  available: number,
  itemWidths: readonly number[],
  moreWidth: number,
): number {
  const total = itemWidths.length;
  if (total === 0 || available <= 0) {
    return 0;
  }

  const sumGaps = (count: number) => (count > 1 ? (count - 1) * NAV_GAP_PX : 0);

  const allWidth =
    itemWidths.reduce((sum, width) => sum + width, 0) + sumGaps(total);
  if (allWidth <= available) {
    return total;
  }

  let used = 0;
  let visible = 0;
  for (let index = 0; index < total; index += 1) {
    const width = itemWidths[index] ?? 0;
    const gapBefore = visible > 0 ? NAV_GAP_PX : 0;
    const withItem = used + gapBefore + width;
    const withMore = withItem + NAV_GAP_PX + moreWidth;
    if (withMore <= available) {
      used = withItem;
      visible = index + 1;
      continue;
    }
    break;
  }

  if (visible === 0 && (itemWidths[0] ?? 0) + NAV_GAP_PX + moreWidth <= available) {
    return 1;
  }
  return visible;
}
