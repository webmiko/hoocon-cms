import { Link, useSearchParams } from "react-router-dom";
import { useMemo, useState } from "react";

import { Breadcrumbs } from "../components/Breadcrumbs";
import { Seo } from "../components/Seo";
import { api, type SearchResultItem } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { softBreak } from "../utils/softBreak";
import styles from "./SearchPage.module.css";

const TYPE_LABEL: Record<string, string> = {
  sku: "Товар",
  article: "Статья",
  news: "Новость",
  page: "Страница",
};

type AppendState = {
  key: string;
  items: SearchResultItem[];
  lastPage: number;
  hasNext: boolean;
};

type LoadMoreUi = {
  key: string;
  loading: boolean;
  error: string | null;
};

/**
 * Search results page (/search/?q=...&page=...).
 *
 * Reads `q` and `page` from the URL query string (shareable, back/forward works).
 * Calls GET /api/search/?q=...&page=... and renders a ranked, paginated list
 * of SKUs, Articles, News, and Pages. Spec: ПЛАН §6 Iter 4;
 * docs/readiness-backend-ux.md §2.3.
 */
export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";
  const page = parseInt(searchParams.get("page") ?? "1", 10) || 1;
  const listKey = `${q}|${page}`;

  const { data, loading, error } = useAsync(
    () => (q ? api.search(q, page) : Promise.resolve(null)),
    [q, page],
  );

  const [append, setAppend] = useState<AppendState>({
    key: "",
    items: [],
    lastPage: 1,
    hasNext: false,
  });
  const [loadMoreUi, setLoadMoreUi] = useState<LoadMoreUi>({
    key: "",
    loading: false,
    error: null,
  });

  const appendLastPage = append.key === listKey ? append.lastPage : page;
  const appendHasNext =
    append.key === listKey ? append.hasNext : Boolean(data?.next);
  const loadingMore = loadMoreUi.key === listKey && loadMoreUi.loading;
  const loadMoreError = loadMoreUi.key === listKey ? loadMoreUi.error : null;
  const hasPrev = Boolean(data?.previous) || page > 1;

  const displayedResults = useMemo(() => {
    const base = data?.results ?? [];
    const extras = append.key === listKey ? append.items : [];
    if (extras.length === 0) return base;
    const seen = new Set(base.map((item) => `${item.type}-${item.slug}`));
    const out = [...base];
    for (const item of extras) {
      const key = `${item.type}-${item.slug}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(item);
    }
    return out;
  }, [data?.results, append, listKey]);

  async function handleShowMore() {
    if (loadingMore || !appendHasNext || !q) return;
    const nextPage = appendLastPage + 1;
    const requestKey = listKey;
    setLoadMoreUi({ key: requestKey, loading: true, error: null });
    try {
      const more = await api.search(q, nextPage);
      setAppend((prev) => {
        const prior = prev.key === requestKey ? prev.items : [];
        return {
          key: requestKey,
          items: [...prior, ...(more.results ?? [])],
          lastPage: nextPage,
          hasNext: Boolean(more.next),
        };
      });
      setLoadMoreUi({ key: requestKey, loading: false, error: null });
    } catch {
      setLoadMoreUi({
        key: requestKey,
        loading: false,
        error: "Не удалось загрузить ещё результаты. Попробуйте снова.",
      });
    }
  }

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    if (key !== "page") next.delete("page");
    setSearchParams(next);
  }

  function handleSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const value = (formData.get("q") as string | null)?.trim() ?? "";
    updateParam("q", value);
  }

  function goToPage(p: number) {
    updateParam("page", p > 1 ? String(p) : "");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <div className={styles.search}>
      <Seo
        title={q ? `Поиск: ${q}` : "Поиск по сайту"}
        description="Поиск по всему сайту Hoocon: каталог, статьи, новости и страницы."
        path="/search"
        noindex
      />
      <Breadcrumbs
        items={[
          { label: "Главная", to: "/" },
          { label: "Поиск" },
        ]}
      />
      <header className={styles.header}>
        <h1 className={styles.title}>Поиск по сайту</h1>

        <form className={styles.form} onSubmit={handleSearch} role="search">
          <input
            type="search"
            name="q"
            defaultValue={q}
            className={styles.input}
            placeholder="Товары, статьи, новости, страницы…"
            aria-label="Поиск по сайту"
            autoFocus
          />
          <button type="submit" className={styles.button}>
            Найти
          </button>
        </form>
      </header>

      {q && (
        <p className={styles.queryInfo}>
          {loading
            ? "Ищем…"
            : `Найдено: ${data?.count ?? 0} по запросу «${q}»`}
        </p>
      )}

      {!q && (
        <p className={styles.hint}>
          Введите запрос. Поиск идёт по всему сайту: каталог, статьи, новости и
          страницы.
        </p>
      )}

      {error && (
        <p className={styles.error}>
          Ошибка поиска. Попробуйте позже или измените запрос.
        </p>
      )}

      {!loading && !error && q && displayedResults.length === 0 && (
        <p className={styles.empty}>
          Ничего не найдено. Попробуйте сформулировать запрос иначе.
        </p>
      )}

      {displayedResults.length > 0 && (
        <>
          <ul className={styles.list}>
            {displayedResults.map((item) => (
              <li key={`${item.type}-${item.slug}`} className={styles.item}>
                <Link to={item.url} className={styles.itemLink}>
                  <span className={`${styles.badge} ${styles[`badge_${item.type}`] ?? ""}`}>
                    {TYPE_LABEL[item.type] ?? item.type}
                  </span>
                  <span className={styles.itemMain}>
                    <span className={styles.itemTitle}>{softBreak(item.title)}</span>
                    {item.snippet ? (
                      <span className={styles.itemSnippet}>
                        {softBreak(item.snippet)}
                      </span>
                    ) : null}
                  </span>
                  <span className={`${styles.itemUrl} text-tech`}>
                    {softBreak(item.url)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>

          <div className={styles.listFooter}>
            {appendHasNext ? (
              <button
                type="button"
                className={styles.showMore}
                disabled={loadingMore}
                onClick={() => {
                  void handleShowMore();
                }}
              >
                {loadingMore ? "Загрузка…" : "Показать ещё"}
              </button>
            ) : null}
            {loadMoreError ? (
              <p className={styles.loadMoreError} role="alert">
                {loadMoreError}
              </p>
            ) : null}
            {(Boolean(data?.next) || hasPrev) && (
              <nav className={styles.pagination} aria-label="Пагинация">
                <button
                  type="button"
                  className={styles.pageButton}
                  disabled={!hasPrev}
                  onClick={() => goToPage(page - 1)}
                >
                  ← Назад
                </button>
                <span className={styles.pageInfo}>Страница {page}</span>
                <button
                  type="button"
                  className={styles.pageButton}
                  disabled={!data?.next}
                  onClick={() => goToPage(page + 1)}
                >
                  Вперёд →
                </button>
              </nav>
            )}
          </div>
        </>
      )}
    </div>
  );
}
