import { Link, useSearchParams } from "react-router-dom";

import { api, type Category, type SKUList } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import styles from "./CatalogPage.module.css";

/**
 * Catalog list page: category filter + search + SKU cards + pagination.
 *
 * Filters sync to query string (?category=...&q=...&page=...) so URLs are
 * shareable and back/forward works. Spec: ПЛАН §6 Iter 4; docs/readiness-backend-ux.md.
 */
export function CatalogPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const category = searchParams.get("category") ?? "";
  const q = searchParams.get("q") ?? "";
  const page = parseInt(searchParams.get("page") ?? "1", 10) || 1;

  // Fetch categories for the sidebar.
  const { data: categoriesData } = useAsync(() => api.categories(), []);

  // Fetch SKUs with current filters.
  const params: Record<string, string> = {};
  if (category) params.category = category;
  if (q) params.q = q;
  if (page > 1) params.page = String(page);

  const { data: skusData, loading, error } = useAsync(() => api.skus(params), [category, q, page]);

  const categories: Category[] = categoriesData?.results ?? [];
  const skus: SKUList[] = skusData?.results ?? [];

  function updateFilter(key: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    // Reset page when filters change.
    if (key !== "page") next.delete("page");
    setSearchParams(next);
  }

  function handleSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const value = (formData.get("q") as string | null)?.trim() ?? "";
    updateFilter("q", value);
  }

  function goToPage(p: number) {
    updateFilter("page", p > 1 ? String(p) : "");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <div className={styles.catalog}>
      <aside className={styles.sidebar}>
        <h2 className={styles.sidebarTitle}>Категории</h2>
        <nav className={styles.categoryNav}>
          <Link
            to="/catalog"
            className={category === "" ? styles.categoryLinkActive : styles.categoryLink}
            onClick={() => updateFilter("category", "")}
          >
            Все категории
          </Link>
          {categories.map((cat) => (
            <Link
              key={cat.slug}
              to={`/catalog?category=${encodeURIComponent(cat.slug)}`}
              className={category === cat.slug ? styles.categoryLinkActive : styles.categoryLink}
              onClick={() => updateFilter("category", cat.slug)}
            >
              {cat.name}
            </Link>
          ))}
        </nav>
      </aside>

      <div className={styles.content}>
        <div className={styles.toolbar}>
          <h1 className={styles.title}>
            {category
              ? categories.find((c) => c.slug === category)?.name ?? "Каталог"
              : "Каталог продукции"}
          </h1>

          <form className={styles.searchForm} onSubmit={handleSearch} role="search">
            <input
              type="search"
              name="q"
              defaultValue={q}
              className={styles.searchInput}
              placeholder="Поиск по названию, артикулу…"
              aria-label="Поиск в каталоге"
            />
            <button type="submit" className={styles.searchButton}>
              Найти
            </button>
          </form>
        </div>

        {q && (
          <p className={styles.searchInfo}>
            Результаты по запросу: <strong>«{q}»</strong>{" "}
            <button className={styles.clearSearch} onClick={() => updateFilter("q", "")}>
              очистить
            </button>
          </p>
        )}

        {loading && <p className={styles.status}>Загрузка…</p>}
        {error && <p className={styles.error}>Ошибка загрузки каталога. Попробуйте позже.</p>}

        {!loading && !error && skus.length === 0 && (
          <p className={styles.status}>Ничего не найдено. Попробуйте изменить фильтры.</p>
        )}

        {skus.length > 0 && (
          <>
            <div className={styles.grid}>
              {skus.map((sku) => (
                <Link key={sku.slug} to={`/${sku.slug}/`} className={styles.card}>
                  <h3 className={styles.cardTitle}>{sku.name}</h3>
                  <p className={styles.cardCode}>Артикул: {sku.sku_code}</p>
                  {sku.analog_belimo_code && (
                    <p className={styles.cardAnalog}>Аналог Belimo: {sku.analog_belimo_code}</p>
                  )}
                  {"price" in sku && sku.price && (
                    <p className={styles.cardPrice}>
                      Цена: {sku.price} ₽
                    </p>
                  )}
                  {sku.price_on_request && (
                    <p className={styles.cardPriceOnRequest}>Цена по запросу</p>
                  )}
                </Link>
              ))}
            </div>

            {skusData && (skusData.next || skusData.previous) && (
              <nav className={styles.pagination} aria-label="Пагинация">
                <button
                  className={styles.pageButton}
                  disabled={!skusData.previous || page <= 1}
                  onClick={() => goToPage(page - 1)}
                >
                  ← Назад
                </button>
                <span className={styles.pageInfo}>Страница {page}</span>
                <button
                  className={styles.pageButton}
                  disabled={!skusData.next}
                  onClick={() => goToPage(page + 1)}
                >
                  Вперёд →
                </button>
              </nav>
            )}
          </>
        )}
      </div>
    </div>
  );
}
