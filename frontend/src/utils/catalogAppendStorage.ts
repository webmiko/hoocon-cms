/**
 * Persist catalog «Показать ещё» depth across PDP back-navigation.
 * Spec: restore list length so scroll-to-product can land.
 */

const STORAGE_KEY = "hoocon.catalog.append.v1";

export type CatalogAppendSnapshot = {
  listKey: string;
  lastPage: number;
  hasNext: boolean;
};

function readAll(): Record<string, CatalogAppendSnapshot> {
  if (typeof sessionStorage === "undefined") return {};
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return {};
    return parsed as Record<string, CatalogAppendSnapshot>;
  } catch {
    return {};
  }
}

function writeAll(data: Record<string, CatalogAppendSnapshot>): void {
  if (typeof sessionStorage === "undefined") return;
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {
    // Quota / private mode — ignore.
  }
}

/**
 * Save how many pages were loaded for a catalog filter set.
 */
export function saveCatalogAppend(snapshot: CatalogAppendSnapshot): void {
  if (snapshot.lastPage < 2) {
    const all = readAll();
    if (all[snapshot.listKey]) {
      delete all[snapshot.listKey];
      writeAll(all);
    }
    return;
  }
  const all = readAll();
  all[snapshot.listKey] = snapshot;
  writeAll(all);
}

/**
 * Read saved append depth for a catalog ``listKey``.
 */
export function readCatalogAppend(listKey: string): CatalogAppendSnapshot | null {
  const row = readAll()[listKey];
  if (!row || row.listKey !== listKey) return null;
  if (!Number.isFinite(row.lastPage) || row.lastPage < 2) return null;
  return row;
}
