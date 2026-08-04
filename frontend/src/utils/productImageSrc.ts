/**
 * Prefer lightweight card WebP for list/tiles; fall back to full hero.
 *
 * API: ProductImage.image_card (≤720px) when backfilled; else image.
 */

export type ProductImageRef = {
  image?: string | null;
  image_card?: string | null;
  alt?: string;
};

/** URL for catalog cards, carousels, compare thumbs (mobile-friendly). */
export function productCardImageSrc(
  image: ProductImageRef | null | undefined,
): string | null {
  if (!image) return null;
  const card = image.image_card?.trim();
  if (card) return card;
  const full = image.image?.trim();
  return full || null;
}

/** Full-resolution URL for PDP / lightbox. */
export function productFullImageSrc(
  image: ProductImageRef | null | undefined,
): string | null {
  if (!image) return null;
  const full = image.image?.trim();
  return full || null;
}
