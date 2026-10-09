import { useState } from "react";

import { useAsync, type AsyncRefreshKey } from "./useAsync";

/** DRF page shape; a bare array is treated as the only page. */
export type PagedResponse<T> = { results: T[]; next?: string | null } | T[];

interface Extra<T> {
  key: string;
  items: T[];
  lastPage: number;
  hasNext: boolean | null;
  loading: boolean;
  error: string | null;
}

function emptyExtra<T>(key: string): Extra<T> {
  return { key, items: [], lastPage: 1, hasNext: null, loading: false, error: null };
}

function pageItems<T>(page: PagedResponse<T> | undefined): T[] {
  if (!page) return [];
  return Array.isArray(page) ? page : page.results;
}

function pageHasNext<T>(page: PagedResponse<T> | undefined): boolean {
  return Boolean(page && !Array.isArray(page) && page.next);
}

/**
 * First DRF page via useAsync plus «Показать ещё» for the following pages.
 *
 * Extra pages belong to ``refreshKey``: a new filter drops them, and a
 * late response for the old key is ignored. Items are deduplicated by id
 * because a new publication shifts later pages by one.
 */
export function usePagedList<T extends { id: number | string }>(
  fetchPage: (page: number, signal?: AbortSignal) => Promise<PagedResponse<T>>,
  refreshKey: AsyncRefreshKey = 0,
) {
  const key = String(refreshKey);
  const first = useAsync((signal) => fetchPage(1, signal), refreshKey);
  const [stored, setStored] = useState<Extra<T>>(() => emptyExtra(key));
  const extra = stored.key === key ? stored : emptyExtra<T>(key);

  const seen = new Set<number | string>();
  const items: T[] = [];
  for (const item of [...pageItems(first.data), ...extra.items]) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    items.push(item);
  }
  const hasNext = extra.hasNext ?? pageHasNext(first.data);

  async function loadMore(): Promise<void> {
    if (extra.loading || !hasNext) return;
    const nextPage = extra.lastPage + 1;
    setStored({ ...extra, loading: true, error: null });
    try {
      const data = await fetchPage(nextPage);
      setStored((prev) =>
        prev.key !== key
          ? prev
          : {
              key,
              items: [...prev.items, ...pageItems(data)],
              lastPage: nextPage,
              hasNext: pageHasNext(data),
              loading: false,
              error: null,
            },
      );
    } catch {
      setStored((prev) =>
        prev.key !== key ? prev : { ...prev, loading: false, error: "Не удалось загрузить ещё. Повторите." },
      );
    }
  }

  return {
    items,
    loading: first.loading,
    error: first.error,
    hasNext,
    loadingMore: extra.loading,
    loadMoreError: extra.error,
    loadMore,
  };
}
