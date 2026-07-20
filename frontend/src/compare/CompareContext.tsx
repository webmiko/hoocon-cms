import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { COMPARE_MAX_SKUS } from "./constants";
import {
  mergeSlugsWithItems,
  readCompareStorage,
  writeCompareStorage,
  type CompareItem,
} from "./storage";

export type CompareAddResult = "added" | "removed" | "limit";

interface CompareContextValue {
  items: CompareItem[];
  count: number;
  isInCompare: (slug: string) => boolean;
  toggle: (item: CompareItem) => CompareAddResult;
  remove: (slug: string) => void;
  clear: () => void;
  /** Replace set from URL slugs (shareable link); keeps known meta. */
  hydrateFromSlugs: (slugs: string[]) => void;
  /** Enrich stub rows after compare API returns. */
  enrichFromSkus: (
    skus: Array<{
      slug: string;
      sku_code: string;
      name: string;
      image?: { image?: string } | null;
    }>,
  ) => void;
}

const CompareContext = createContext<CompareContextValue | null>(null);

/**
 * Provider for catalog compare tray (localStorage-backed, max 4).
 */
export function CompareProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<CompareItem[]>(() => readCompareStorage());

  const persist = useCallback((updater: (prev: CompareItem[]) => CompareItem[]) => {
    setItems((prev) => {
      const next = updater(prev);
      writeCompareStorage(next);
      return next;
    });
  }, []);

  const isInCompare = useCallback(
    (slug: string) => items.some((item) => item.slug === slug),
    [items],
  );

  const toggle = useCallback(
    (item: CompareItem): CompareAddResult => {
      const exists = items.some((row) => row.slug === item.slug);
      if (exists) {
        persist((prev) => prev.filter((row) => row.slug !== item.slug));
        return "removed";
      }
      if (items.length >= COMPARE_MAX_SKUS) {
        return "limit";
      }
      persist((prev) => [...prev, item]);
      return "added";
    },
    [items, persist],
  );

  const remove = useCallback(
    (slug: string) => {
      persist((prev) => prev.filter((row) => row.slug !== slug));
    },
    [persist],
  );

  const clear = useCallback(() => {
    persist(() => []);
  }, [persist]);

  const hydrateFromSlugs = useCallback(
    (slugs: string[]) => {
      persist((prev) => {
        const next = mergeSlugsWithItems(slugs, prev);
        if (
          next.length === prev.length &&
          next.every((item, index) => item.slug === prev[index]?.slug)
        ) {
          return prev;
        }
        return next;
      });
    },
    [persist],
  );

  const enrichFromSkus = useCallback(
    (
      skus: Array<{
        slug: string;
        sku_code: string;
        name: string;
        image?: { image?: string } | null;
      }>,
    ) => {
      const bySlug = new Map(
        skus.map((sku) => [
          sku.slug,
          {
            slug: sku.slug,
            sku_code: sku.sku_code,
            name: sku.name,
            image: sku.image?.image ?? null,
          } satisfies CompareItem,
        ]),
      );
      persist((prev) =>
        prev.map((item) => bySlug.get(item.slug) ?? item),
      );
    },
    [persist],
  );

  const value = useMemo(
    () => ({
      items,
      count: items.length,
      isInCompare,
      toggle,
      remove,
      clear,
      hydrateFromSlugs,
      enrichFromSkus,
    }),
    [
      items,
      isInCompare,
      toggle,
      remove,
      clear,
      hydrateFromSlugs,
      enrichFromSkus,
    ],
  );

  return (
    <CompareContext.Provider value={value}>{children}</CompareContext.Provider>
  );
}

/**
 * Access compare tray state. Must be under CompareProvider.
 */
export function useCompare(): CompareContextValue {
  const ctx = useContext(CompareContext);
  if (!ctx) {
    throw new Error("useCompare must be used within CompareProvider");
  }
  return ctx;
}
