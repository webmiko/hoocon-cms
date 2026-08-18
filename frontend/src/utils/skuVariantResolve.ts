/** Resolve H81 (and similar) sibling editions from PDP picker axes. */

export type SiblingEdition = {
  slug: string;
  sku_code: string;
  body: string;
  dn: string;
  ways: string;
  kvs: string;
  voltage: string;
  control: string;
  aux_switch: boolean;
  fault_alarm?: boolean;
  in_stock: boolean;
  in_stock_ma?: boolean;
};

export type VariantSelection = {
  ways: string;
  dn: string;
  kvs: string;
  body: string;
  voltage: string;
  control: string;
};

/** Axes cleared when a parent axis changes (dependent facets). */
const CLEARED_ON_CHANGE: Record<
  keyof VariantSelection,
  readonly (keyof VariantSelection)[]
> = {
  // Keep DN when switching 2↔3 if that DN exists for the new ways.
  ways: ["kvs", "body"],
  dn: ["kvs", "body"],
  kvs: ["body"],
  body: [],
  voltage: [],
  control: [],
};

/** Match priority when scoring candidates (higher weight first). */
const SCORE_WEIGHT: Record<keyof VariantSelection, number> = {
  body: 32,
  kvs: 16,
  dn: 12,
  ways: 10,
  voltage: 8,
  control: 8,
};

export function selectionFromSibling(row: SiblingEdition): VariantSelection {
  return {
    ways: row.ways,
    dn: row.dn,
    kvs: row.kvs,
    body: row.body,
    voltage: row.voltage,
    control: row.control,
  };
}

function axisEquals(
  key: keyof VariantSelection,
  row: SiblingEdition,
  want: string,
): boolean {
  if (!want) return true;
  const raw = String(row[key] ?? "");
  if (key === "body" || key === "control") {
    return raw.toUpperCase() === want.toUpperCase();
  }
  return raw === want;
}

/**
 * Pick the best existing sibling for a selection.
 *
 * ``locked`` axes (just changed by the user) must match when any candidate
 * exists; remaining axes are soft preferences. Always returns a row when
 * ``siblings`` is non-empty so the picker never gets stuck.
 */
export function resolveSiblingEdition(
  siblings: SiblingEdition[],
  selection: VariantSelection,
  locked: Partial<VariantSelection> = {},
): SiblingEdition | null {
  if (!siblings.length) return null;

  const lockedEntries = (
    Object.entries(locked) as [keyof VariantSelection, string][]
  ).filter(([, value]) => Boolean(String(value || "").trim()));

  let pool = siblings;
  if (lockedEntries.length) {
    const filtered = siblings.filter((row) =>
      lockedEntries.every(([key, value]) => axisEquals(key, row, value.trim())),
    );
    if (filtered.length) {
      pool = filtered;
    }
  }

  const want: VariantSelection = {
    ways: selection.ways.trim(),
    dn: selection.dn.trim(),
    kvs: selection.kvs.trim(),
    body: selection.body.trim(),
    voltage: selection.voltage.trim(),
    control: selection.control.trim(),
  };

  let best: SiblingEdition | null = null;
  let bestScore = -1;
  for (const row of pool) {
    let score = 0;
    for (const key of Object.keys(SCORE_WEIGHT) as (keyof VariantSelection)[]) {
      const preferred = want[key];
      if (!preferred) continue;
      if (axisEquals(key, row, preferred)) {
        score += SCORE_WEIGHT[key];
      }
    }
    if (score > bestScore) {
      bestScore = score;
      best = row;
    }
  }
  return best ?? pool[0] ?? null;
}

/**
 * Find the sibling slug matching the selected axes (compat helper).
 */
export function resolveSiblingSlug(
  siblings: SiblingEdition[],
  selection: VariantSelection,
  locked: Partial<VariantSelection> = {},
): string | null {
  return resolveSiblingEdition(siblings, selection, locked)?.slug ?? null;
}

/**
 * Apply a partial axis change and coerce to a real sibling edition.
 *
 * Clears dependent axes (e.g. DN change drops Kvs/body) so incompatible
 * leftovers cannot block navigation.
 */
export function applyVariantPatch(
  siblings: SiblingEdition[],
  selection: VariantSelection,
  partial: Partial<VariantSelection>,
): SiblingEdition | null {
  if (!siblings.length) return null;
  const next: VariantSelection = { ...selection, ...partial };
  for (const key of Object.keys(partial) as (keyof VariantSelection)[]) {
    for (const dep of CLEARED_ON_CHANGE[key]) {
      if (!(dep in partial)) {
        next[dep] = "";
      }
    }
  }
  return resolveSiblingEdition(siblings, next, partial);
}

/** Bodies available for the current ways+dn (and optional kvs) filter. */
export function bodiesForSelection(
  siblings: SiblingEdition[],
  selection: Pick<VariantSelection, "ways" | "dn" | "kvs">,
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const row of siblings) {
    if (selection.ways && row.ways !== selection.ways) continue;
    if (selection.dn && row.dn !== selection.dn) continue;
    if (selection.kvs && row.kvs !== selection.kvs) continue;
    if (!row.body || seen.has(row.body)) continue;
    seen.add(row.body);
    out.push(row.body);
  }
  return out;
}
