/**
 * Catalog photo-block purpose for studio gradient washes.
 *
 * Maps category slugs → air / smoke / fire / valve. Used on PDP hero/gallery
 * and catalog cards so transparent product WebP sits on a purpose-tinted wash.
 */

export type MediaPurpose = "air" | "smoke" | "fire" | "valve";

/**
 * Resolve media purpose from a catalog category slug.
 *
 * Args:
 *   categorySlug: Category.slug from the API (may be empty).
 *
 * Returns:
 *   Purpose key for CSS ``data-purpose`` on photo blocks.
 */
export function mediaPurposeFromCategory(
  categorySlug: string | null | undefined,
): MediaPurpose {
  const slug = (categorySlug || "").toLowerCase();
  if (!slug) {
    return "valve";
  }
  if (slug.includes("sharov")) {
    return "valve";
  }
  if (slug.includes("protivopozhar")) {
    return "fire";
  }
  if (slug.includes("dymoudalen") || slug.includes("dymov")) {
    return "smoke";
  }
  // Fast / accelerated drives → smoke dampers.
  if (slug.includes("uskoren")) {
    return "smoke";
  }
  // Air before spring-return: «bez-pruzhinnogo» still contains «pruzhinn».
  if (slug.includes("vozdush")) {
    return "air";
  }
  // Spring-return actuators → fire dampers (Belimo RU naming).
  if (slug.includes("pruzhinnym") || slug.includes("pruzhinny")) {
    return "fire";
  }
  return "valve";
}
