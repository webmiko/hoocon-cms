/** Public availability labels for catalog cards / PDP (no raw qty). */

/**
 * Storefront stock label.
 *
 * Out-of-stock SKUs are sold to order (never shown as «нет в наличии»),
 * including cast-iron kits that are never warehouse stock.
 *
 * Args:
 *   inStock: API ``in_stock`` flag; missing treated as not on hand.
 *
 * Returns:
 *   «Есть в наличии» or «Под заказ».
 */
export function stockAvailabilityLabel(inStock: boolean | undefined): string {
  return inStock ? "Есть в наличии" : "Под заказ";
}
