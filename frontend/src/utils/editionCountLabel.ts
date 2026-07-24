/** Russian plural for catalog «N вариантов». */

/**
 * Format edition count for family catalog cards.
 *
 * Args:
 *   count: Published SKU count on the Product (≥ 1).
 *
 * Returns:
 *   ``2 варианта`` / ``5 вариантов`` / empty when count ≤ 1.
 */
export function formatEditionCountLabel(count: number): string {
  const n = Math.floor(Number(count) || 0);
  if (n <= 1) return "";
  const mod100 = n % 100;
  const mod10 = n % 10;
  if (mod100 >= 11 && mod100 <= 14) {
    return `${n} вариантов`;
  }
  if (mod10 === 1) {
    return `${n} вариант`;
  }
  if (mod10 >= 2 && mod10 <= 4) {
    return `${n} варианта`;
  }
  return `${n} вариантов`;
}
