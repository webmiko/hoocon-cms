/** Canonical nested catalog paths (SEO: one page per SKU). */

export function catalogCategoryPath(categorySlug: string): string {
  const slug = categorySlug.trim().replace(/^\/+|\/+$/g, "");
  return slug ? `/catalog/${slug}` : "/catalog";
}

export function catalogSkuPath(categorySlug: string, skuSlug: string): string {
  const cat = categorySlug.trim().replace(/^\/+|\/+$/g, "");
  const sku = skuSlug.trim().replace(/^\/+|\/+$/g, "");
  if (!cat || !sku) return "/catalog";
  return `/catalog/${cat}/${sku}`;
}

/** Path for a list/detail SKU card. Falls back to /catalog if category missing. */
export function catalogPathForSku(sku: {
  category_slug?: string | null;
  slug?: string | null;
}): string {
  const cat = sku.category_slug ?? "";
  const slug = sku.slug ?? "";
  if (!cat || !slug) return "/catalog";
  return catalogSkuPath(cat, slug);
}
