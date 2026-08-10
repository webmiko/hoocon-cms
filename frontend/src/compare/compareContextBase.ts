import { createContext } from "react";

import type { CompareItem } from "./storage";

export type CompareAddResult = "added" | "removed" | "limit";

export interface CompareContextValue {
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

export const CompareContext = createContext<CompareContextValue | null>(null);
