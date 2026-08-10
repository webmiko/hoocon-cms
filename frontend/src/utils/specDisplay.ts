/**
 * Unit to show after a ТТХ value, or empty if the value already includes it.
 * Avoids «≤ 100 сек с» / «≤ 100 с с» when Attribute.unit is «с».
 */
export function specDisplayUnit(value: string, unit: string | undefined | null): string {
  const cleaned = (unit ?? "").trim();
  if (!cleaned) return "";
  const text = value ?? "";
  if (cleaned === "с") {
    // «≤ 100 с» / «≤ 100 сек» — unit already in the value.
    if (/\d\s*с(?:\s|$|[)(,./])/u.test(text)) return "";
    if (/сек/i.test(text)) return "";
    return cleaned;
  }
  if (text.toLocaleLowerCase("ru").includes(cleaned.toLocaleLowerCase("ru"))) {
    return "";
  }
  return cleaned;
}
