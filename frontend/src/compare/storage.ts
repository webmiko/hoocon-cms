import {
  COMPARE_MAX_SKUS,
  COMPARE_STORAGE_KEY,
} from "./constants";

/** Compact SKU ref for tray / localStorage. */
export interface CompareItem {
  slug: string;
  sku_code: string;
  name: string;
  image?: string | null;
}

interface CompareStoragePayload {
  items: CompareItem[];
  updatedAt: string;
}

/**
 * Parse ``?skus=a,b,c`` into ordered unique slugs.
 */
export function parseCompareSlugsParam(raw: string | null): string[] {
  if (!raw) return [];
  const seen = new Set<string>();
  const ordered: string[] = [];
  for (const part of raw.split(",")) {
    const slug = part.trim();
    if (!slug || seen.has(slug)) continue;
    seen.add(slug);
    ordered.push(slug);
  }
  return ordered;
}

/**
 * Build shareable compare query (preserves order, max COMPARE_MAX_SKUS).
 */
export function buildCompareSearch(slugs: string[]): string {
  const unique = parseCompareSlugsParam(slugs.join(",")).slice(
    0,
    COMPARE_MAX_SKUS,
  );
  if (unique.length === 0) return "";
  return `?skus=${unique.map(encodeURIComponent).join(",")}`;
}

/**
 * Read compare set from localStorage (empty on error / SSR).
 */
export function readCompareStorage(): CompareItem[] {
  if (typeof localStorage === "undefined") return [];
  try {
    const raw = localStorage.getItem(COMPARE_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as CompareStoragePayload;
    if (!Array.isArray(parsed.items)) return [];
    return parsed.items
      .filter(
        (item): item is CompareItem =>
          Boolean(item && typeof item.slug === "string" && item.slug),
      )
      .slice(0, COMPARE_MAX_SKUS)
      .map((item) => ({
        slug: item.slug,
        sku_code: String(item.sku_code || item.slug),
        name: String(item.name || item.sku_code || item.slug),
        image: item.image ?? null,
      }));
  } catch {
    return [];
  }
}

/**
 * Persist compare set.
 */
export function writeCompareStorage(items: CompareItem[]): void {
  if (typeof localStorage === "undefined") return;
  const payload: CompareStoragePayload = {
    items: items.slice(0, COMPARE_MAX_SKUS),
    updatedAt: new Date().toISOString(),
  };
  try {
    localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // Quota / private mode — ignore.
  }
}

/**
 * Merge URL slug order with known meta from storage / stubs.
 */
export function mergeSlugsWithItems(
  slugs: string[],
  known: CompareItem[],
): CompareItem[] {
  const bySlug = new Map(known.map((item) => [item.slug, item]));
  return slugs.slice(0, COMPARE_MAX_SKUS).map((slug) => {
    const existing = bySlug.get(slug);
    if (existing) return existing;
    return { slug, sku_code: slug, name: slug, image: null };
  });
}
