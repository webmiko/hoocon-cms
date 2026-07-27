/**
 * Remember which catalog card the user opened, for back-navigation restore.
 * Spec: mobile catalog → PDP → back should land on the same card.
 */

const STORAGE_KEY = "hoocon.catalog.focus.v1";

export type CatalogFocusAnchor = {
  /** ``pathname + search`` of the catalog list. */
  path: string;
  slug: string;
  y: number;
};

function pathKey(pathname: string, search: string): string {
  return `${pathname}${search}`;
}

/**
 * Store focus when the user opens a catalog card.
 */
export function saveCatalogFocus(anchor: CatalogFocusAnchor): void {
  if (typeof sessionStorage === "undefined") return;
  if (!anchor.slug) return;
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(anchor));
  } catch {
    // ignore quota / private mode
  }
}

/**
 * Read focus for the current catalog path, if any.
 */
export function readCatalogFocus(
  pathname: string,
  search: string,
): CatalogFocusAnchor | null {
  if (typeof sessionStorage === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CatalogFocusAnchor;
    if (!parsed?.slug || typeof parsed.slug !== "string") return null;
    if (parsed.path !== pathKey(pathname, search)) return null;
    return {
      path: parsed.path,
      slug: parsed.slug,
      y: Number.isFinite(parsed.y) ? Math.max(0, Math.round(parsed.y)) : 0,
    };
  } catch {
    return null;
  }
}

export function catalogFocusPath(pathname: string, search: string): string {
  return pathKey(pathname, search);
}

/** DOM id for a catalog card (scroll target). */
export function catalogSkuDomId(slug: string): string {
  return `catalog-sku-${slug}`;
}
