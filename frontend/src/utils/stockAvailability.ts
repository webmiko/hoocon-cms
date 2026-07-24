/** Public availability labels for catalog cards / PDP (no raw qty). */

export function stockAvailabilityLabel(inStock: boolean | undefined): string {
  return inStock ? "Есть в наличии" : "Нет в наличии";
}
