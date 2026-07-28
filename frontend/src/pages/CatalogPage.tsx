import { Link, useLocation, useNavigate, useNavigationType, useParams, useSearchParams } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";

import { Seo } from "../components/Seo";
import { CatalogSkeleton } from "../components/CatalogSkeleton";
import { Breadcrumbs } from "../components/Breadcrumbs";
import {
  api,
  type CatalogFacet,
  type Category,
  type SKUList,
} from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { facetLabelShort, facetValueShort } from "../utils/facetDisplay";
import { buildBreadcrumbJsonLd } from "../utils/jsonLd";
import { parseProductDescription } from "../utils/parseDescription";
import { CatalogSkuCard } from "../components/CatalogSkuCard";
import { InstructionText } from "../components/InstructionText";
import { softBreak } from "../utils/softBreak";
import {
  catalogCategoryPath,
} from "../utils/catalogPaths";
import { collapseH81CatalogSkus } from "../utils/h81CatalogCollapse";
import {
  readCatalogAppend,
  saveCatalogAppend,
} from "../utils/catalogAppendStorage";
import {
  catalogSkuDomId,
  readCatalogFocus,
} from "../utils/catalogFocus";
import {
  readScrollPosition,
  restoreScrollPosition,
  restoreScrollToElement,
} from "../utils/scrollPositions";
import styles from "./CatalogPage.module.css";

/** Facet query keys synced to the URL (backend catalog.facets). */
const FACET_KEYS = [
  "moment",
  "voltage",
  "control",
  "area",
  "aux_switch",
  "temp_sensor",
  "dn",
  "ways",
  "kvs",
  "material",
  "analog",
] as const;

type FacetKey = (typeof FACET_KEYS)[number];

type AppendState = {
  key: string;
  items: SKUList[];
  lastPage: number;
  hasNext: boolean;
};

type LoadMoreUi = {
  key: string;
  loading: boolean;
  error: string | null;
};

/**
 * Catalog list: categories + ТТХ facets + compact SKU cards.
 *
 * Category lives in the path (``/catalog/{slug}``); facets/q/page in the query.
 * Legacy ``?category=`` redirects to the nested path.
 */
export function CatalogPage() {
  const { categorySlug: categoryFromPath = "" } = useParams<{
    categorySlug?: string;
  }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const navigationType = useNavigationType();
  const location = useLocation();

  // Legacy share links: /catalog?category=… → /catalog/…
  useEffect(() => {
    const legacy = searchParams.get("category");
    if (!legacy || categoryFromPath) return;
    const next = new URLSearchParams(searchParams);
    next.delete("category");
    const qs = next.toString();
    navigate(
      `${catalogCategoryPath(legacy)}${qs ? `?${qs}` : ""}`,
      { replace: true },
    );
  }, [searchParams, categoryFromPath, navigate]);

  const category = categoryFromPath;
  const q = searchParams.get("q") ?? "";
  const page = parseInt(searchParams.get("page") ?? "1", 10) || 1;
  const inStockOnly = ["1", "true", "yes", "on"].includes(
    (searchParams.get("in_stock") ?? "").toLowerCase(),
  );
  const newOnly = ["1", "true", "yes", "on"].includes(
    (searchParams.get("new") ?? "").toLowerCase(),
  );

  const activeFacets: Partial<Record<FacetKey, string>> = {};
  for (const key of FACET_KEYS) {
    const value = searchParams.get(key);
    if (value) activeFacets[key] = value;
  }

  const { data: categoriesData } = useAsync(
    () => api.categories(),
    0,
    "catalog:categories",
  );
  const { data: facetsData } = useAsync(
    () => api.facets(category ? { category } : undefined),
    category,
    `catalog:facets:${category || "all"}`,
  );

  const params: Record<string, string> = {};
  if (category) params.category = category;
  if (q) params.q = q;
  if (page > 1) params.page = String(page);
  if (inStockOnly) params.in_stock = "1";
  if (newOnly) params.new = "1";
  for (const [key, value] of Object.entries(activeFacets)) {
    if (value) params[key] = value;
  }

  const facetKey = FACET_KEYS.map((k) => activeFacets[k] ?? "").join("|");
  const listKey = `${category}|${q}|${page}|${facetKey}|${inStockOnly ? "1" : "0"}|${newOnly ? "1" : "0"}`;
  const { data: skusData, loading, error } = useAsync(
    () => api.skus(params),
    listKey,
    `catalog:skus:${listKey}`,
  );

  const categories: Category[] = categoriesData?.results ?? [];
  const facets: CatalogFacet[] = facetsData?.results ?? [];
  const activeCount =
    Object.keys(activeFacets).length +
    (q ? 1 : 0) +
    (category ? 1 : 0) +
    (inStockOnly ? 1 : 0) +
    (newOnly ? 1 : 0);
  const activeCategory = categories.find((c) => c.slug === category);

  // «Показать ещё»: append next DRF pages (PAGE_SIZE=20) without replacing.
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
    append.key === listKey ? append.hasNext : Boolean(skusData?.next);
  const loadingMore = loadMoreUi.key === listKey && loadMoreUi.loading;
  const loadMoreError =
    loadMoreUi.key === listKey ? loadMoreUi.error : null;

  const displayedSkus = useMemo(() => {
    const base = (skusData?.results ?? []) as SKUList[];
    const extras = append.key === listKey ? append.items : [];
    let merged = base;
    if (extras.length > 0) {
      const seen = new Set(base.map((s) => s.slug));
      const out = [...base];
      for (const sku of extras) {
        if (seen.has(sku.slug)) continue;
        seen.add(sku.slug);
        out.push(sku);
      }
      merged = out;
    }
    return collapseH81CatalogSkus(merged);
  }, [skusData?.results, append, listKey]);

  // Persist «Показать ещё» depth so back from PDP can rebuild the list.
  useEffect(() => {
    if (append.key !== listKey) return;
    saveCatalogAppend({
      listKey,
      lastPage: append.lastPage,
      hasNext: append.hasNext,
    });
  }, [append, listKey]);

  // After list paint on back: land on the opened card (or saved Y).
  useEffect(() => {
    if (navigationType !== "POP") return;
    if (loading || displayedSkus.length === 0) return;

    const focus = readCatalogFocus(location.pathname, location.search);
    if (focus?.slug) {
      const el = document.getElementById(catalogSkuDomId(focus.slug));
      if (el instanceof HTMLElement) {
        return restoreScrollToElement(el, 4500);
      }
      // Card not in DOM yet — wait for «Показать ещё» restore, do not Y-jump.
      const depth = readCatalogAppend(listKey);
      if (depth && depth.lastPage > page) {
        return;
      }
      if (append.key === listKey && append.lastPage > page) {
        // Still merging extras — wait for next length change.
        if (!displayedSkus.some((s) => s.slug === focus.slug)) {
          return;
        }
      }
    }

    const y =
      focus?.y ||
      readScrollPosition(location.key) ||
      0;
    if (y <= 0) return;
    return restoreScrollPosition(y, 4500);
  }, [
    navigationType,
    loading,
    displayedSkus,
    listKey,
    page,
    append.key,
    append.lastPage,
    location.key,
    location.pathname,
    location.search,
  ]);

  // On back/forward: reload pages 2..N that were open before leaving.
  useEffect(() => {
    if (navigationType !== "POP") return;
    if (loading || !skusData) return;
    const saved = readCatalogAppend(listKey);
    if (!saved || saved.lastPage <= page) return;
    if (append.key === listKey && append.lastPage >= saved.lastPage) return;

    let cancelled = false;
    const categoryParam = category;
    const qParam = q;
    const inStockParam = inStockOnly;
    const newParam = newOnly;
    const basePage = page;
    const facetPairs = FACET_KEYS.map(
      (key) => [key, searchParams.get(key) ?? ""] as const,
    ).filter(([, value]) => Boolean(value));

    void (async () => {
      const collected: SKUList[] = [];
      let lastLoaded = basePage;
      let hasNext = Boolean(skusData.next);
      for (let p = basePage + 1; p <= saved.lastPage; p += 1) {
        const request: Record<string, string> = { page: String(p) };
        if (categoryParam) request.category = categoryParam;
        if (qParam) request.q = qParam;
        if (inStockParam) request.in_stock = "1";
        if (newParam) request.new = "1";
        for (const [key, value] of facetPairs) {
          request[key] = value;
        }
        try {
          const data = await api.skus(request);
          if (cancelled) return;
          collected.push(...((data.results ?? []) as SKUList[]));
          lastLoaded = p;
          hasNext = Boolean(data.next);
        } catch {
          break;
        }
      }
      if (cancelled || collected.length === 0) return;
      setAppend({
        key: listKey,
        items: collected,
        lastPage: lastLoaded,
        hasNext,
      });
      // Card may appear only after append — re-focus on next paint via the
      // list effect (displayedSkus.length change). Also nudge immediately.
      const focus = readCatalogFocus(location.pathname, location.search);
      if (focus?.slug) {
        window.requestAnimationFrame(() => {
          const el = document.getElementById(catalogSkuDomId(focus.slug));
          if (el instanceof HTMLElement) {
            restoreScrollToElement(el, 4500);
          }
        });
      } else {
        const y = readScrollPosition(location.key);
        if (y !== undefined && y > 0) {
          restoreScrollPosition(y, 4500);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [
    navigationType,
    loading,
    skusData,
    listKey,
    page,
    append.key,
    append.lastPage,
    category,
    q,
    inStockOnly,
    newOnly,
    facetKey,
    searchParams,
    location.key,
    location.pathname,
    location.search,
  ]);

  async function handleShowMore() {
    if (loadingMore || !appendHasNext) return;
    const nextPage = appendLastPage + 1;
    const requestKey = listKey;
    setLoadMoreUi({ key: requestKey, loading: true, error: null });
    try {
      const data = await api.skus({ ...params, page: String(nextPage) });
      const batch = (data.results ?? []) as SKUList[];
      setAppend((prev) => {
        const prior = prev.key === requestKey ? prev.items : [];
        return {
          key: requestKey,
          items: [...prior, ...batch],
          lastPage: nextPage,
          hasNext: Boolean(data.next),
        };
      });
      setLoadMoreUi({ key: requestKey, loading: false, error: null });
    } catch {
      setLoadMoreUi({
        key: requestKey,
        loading: false,
        error: "Не удалось загрузить ещё товары. Попробуйте снова.",
      });
    }
  }

  function updateFilter(key: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    if (key !== "page") next.delete("page");
    setSearchParams(next);
  }

  function clearAllFilters() {
    if (category) {
      navigate("/catalog");
      return;
    }
    setSearchParams(new URLSearchParams());
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

  const filterHead = (
    <div className={styles.filterPanelHead}>
      <h2 className={styles.filterPanelTitle}>Фильтры</h2>
      {activeCount > 0 ? (
        <button
          type="button"
          className={styles.clearFacets}
          onClick={clearAllFilters}
        >
          Сбросить
        </button>
      ) : null}
    </div>
  );

  const filterSections = (
    <>
      <details className={styles.filterSection} open>
        <summary className={styles.filterSummary}>
          <span className={styles.filterSummaryLabel}>Категория</span>
          <span
            className={
              category
                ? styles.filterSummaryValueActive
                : styles.filterSummaryValue
            }
          >
            {activeCategory ? softBreak(activeCategory.name) : "Все"}
          </span>
        </summary>
        <nav className={styles.categoryNav} aria-label="Категории каталога">
          <Link
            to="/catalog"
            className={
              category === "" ? styles.optionRowActive : styles.optionRow
            }
          >
            <span className={styles.optionText}>Все категории</span>
          </Link>
          {categories.map((cat) => (
            <Link
              key={cat.slug}
              to={catalogCategoryPath(cat.slug)}
              className={
                category === cat.slug ? styles.optionRowActive : styles.optionRow
              }
            >
              <span className={styles.optionText}>{softBreak(cat.name)}</span>
            </Link>
          ))}
        </nav>
      </details>

      <div className={styles.filterSection}>
        <button
          type="button"
          className={
            inStockOnly ? styles.optionRowActive : styles.optionRow
          }
          aria-pressed={inStockOnly}
          onClick={() => updateFilter("in_stock", inStockOnly ? "" : "1")}
        >
          <span className={styles.optionText}>Только в наличии</span>
        </button>
        <button
          type="button"
          className={newOnly ? styles.optionRowActive : styles.optionRow}
          aria-pressed={newOnly}
          onClick={() => updateFilter("new", newOnly ? "" : "1")}
        >
          <span className={styles.optionText}>Новинки</span>
        </button>
      </div>

      {facets.map((facet) => {
        const selected = activeFacets[facet.key as FacetKey];
        const shortLabel = facetLabelShort(facet.key, facet.label);
        return (
          <details key={facet.key} className={styles.filterSection}>
            <summary className={styles.filterSummary}>
              <span className={styles.filterSummaryLabel}>{shortLabel}</span>
              <span
                className={
                  selected
                    ? styles.filterSummaryValueActive
                    : styles.filterSummaryValue
                }
              >
                {selected ? facetValueShort(facet.key, selected) : "Любое"}
              </span>
            </summary>
            <ul className={styles.optionList}>
              {facet.values.map((item) => {
                const isOn = selected === item.value;
                return (
                  <li key={item.value}>
                    <button
                      type="button"
                      className={isOn ? styles.optionRowActive : styles.optionRow}
                      aria-pressed={isOn}
                      title={item.value}
                      onClick={() =>
                        updateFilter(facet.key, isOn ? "" : item.value)
                      }
                    >
                      <span className={styles.optionText}>
                        {facetValueShort(facet.key, item.value)}
                      </span>
                      <span className={styles.optionCount}>{item.count}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </details>
        );
      })}
    </>
  );

  return (
    <div className={styles.page}>
      <Seo
        title={
          activeCategory
            ? activeCategory.name
            : "Каталог электроприводов вентиляции и кондиционирования"
        }
        description={
          "Каталог электроприводов Hoocon для вентиляции и кондиционирования. "
          + "Фильтры по моменту, напряжению, типу; паспорта PDF; подбор аналогов Belimo."
        }
        path={category ? catalogCategoryPath(category) : "/catalog"}
        jsonLd={[
          buildBreadcrumbJsonLd([
            { name: "Главная", path: "/" },
            { name: "Каталог", path: "/catalog" },
            ...(activeCategory
              ? [
                  {
                    name: activeCategory.name,
                    path: catalogCategoryPath(activeCategory.slug),
                  },
                ]
              : []),
          ]),
        ]}
      />

      <Breadcrumbs
        items={[
          { label: "Главная", to: "/" },
          {
            label: "Каталог",
            to: activeCategory ? "/catalog" : undefined,
          },
          ...(activeCategory
            ? [{ label: activeCategory.name }]
            : []),
        ]}
      />

      <div className={styles.catalog}>
      <aside className={styles.sidebar} aria-label="Фильтры каталога">
        <div className={styles.filtersDesktop}>
          <div className={styles.filterStickyHead}>{filterHead}</div>
          <div className={styles.filterScroll}>
            <div className={styles.filterPanel}>{filterSections}</div>
          </div>
        </div>
        <details className={styles.filtersMobile}>
          <summary className={styles.filtersMobileSummary}>
            <span>Фильтры</span>
            {activeCount > 0 ? (
              <span className={styles.filtersMobileBadge}>{activeCount}</span>
            ) : null}
          </summary>
          <div className={styles.filterPanel}>
            {filterHead}
            {filterSections}
          </div>
        </details>
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

        {activeCount > 0 ? (
          <div className={styles.activeTags} aria-label="Активные фильтры">
            {category && activeCategory ? (
              <button
                type="button"
                className={styles.activeTag}
                onClick={() => navigate("/catalog")}
              >
                <span className={styles.activeTagLabel}>Категория</span>
                <span className={styles.activeTagValue}>
                  {softBreak(activeCategory.name)}
                </span>
                <span className={styles.activeTagRemove} aria-hidden="true">
                  ×
                </span>
              </button>
            ) : null}
            {q ? (
              <button
                type="button"
                className={styles.activeTag}
                onClick={() => updateFilter("q", "")}
              >
                <span className={styles.activeTagLabel}>Поиск</span>
                <span className={styles.activeTagValue}>{q}</span>
                <span className={styles.activeTagRemove} aria-hidden="true">
                  ×
                </span>
              </button>
            ) : null}
            {inStockOnly ? (
              <button
                type="button"
                className={styles.activeTag}
                onClick={() => updateFilter("in_stock", "")}
              >
                <span className={styles.activeTagLabel}>Наличие</span>
                <span className={styles.activeTagValue}>Есть в наличии</span>
                <span className={styles.activeTagRemove} aria-hidden="true">
                  ×
                </span>
              </button>
            ) : null}
            {newOnly ? (
              <button
                type="button"
                className={styles.activeTag}
                onClick={() => updateFilter("new", "")}
              >
                <span className={styles.activeTagLabel}>Подборка</span>
                <span className={styles.activeTagValue}>Новинки</span>
                <span className={styles.activeTagRemove} aria-hidden="true">
                  ×
                </span>
              </button>
            ) : null}
            {FACET_KEYS.map((key) => {
              const value = activeFacets[key];
              if (!value) return null;
              const facetMeta = facets.find((f) => f.key === key);
              return (
                <button
                  key={key}
                  type="button"
                  className={styles.activeTag}
                  onClick={() => updateFilter(key, "")}
                >
                  <span className={styles.activeTagLabel}>
                    {facetLabelShort(key, facetMeta?.label ?? key)}
                  </span>
                  <span className={styles.activeTagValue}>
                    {facetValueShort(key, value)}
                  </span>
                  <span className={styles.activeTagRemove} aria-hidden="true">
                    ×
                  </span>
                </button>
              );
            })}
            <button
              type="button"
              className={styles.clearSearch}
              onClick={clearAllFilters}
            >
              Очистить всё
            </button>
          </div>
        ) : null}

        {category ? (
          <CategoryOverview
            category={categories.find((c) => c.slug === category)}
          />
        ) : null}

        {loading && displayedSkus.length === 0 && <CatalogSkeleton />}
        {error && displayedSkus.length === 0 && (
          <p className={styles.error}>Ошибка загрузки каталога. Попробуйте позже.</p>
        )}

        {!loading && !error && displayedSkus.length === 0 && (
          <div className={styles.emptyState}>
            <span className={styles.emptyIcon} aria-hidden="true">
              ∅
            </span>
            <p className={styles.emptyTitle}>Ничего не найдено</p>
            <p className={styles.emptyHint}>
              Попробуйте изменить фильтры или сбросить выбор.
            </p>
            {activeCount > 0 && (
              <button
                type="button"
                className={styles.emptyCta}
                onClick={clearAllFilters}
              >
                Сбросить фильтры
              </button>
            )}
          </div>
        )}

        {displayedSkus.length > 0 && (
          <>
            <div
              className={styles.grid}
              aria-busy={loading || undefined}
            >
              {displayedSkus.map((sku) => (
                <CatalogSkuCard key={sku.slug} sku={sku} />
              ))}
            </div>

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
              {skusData && (skusData.next || skusData.previous) ? (
                <nav className={styles.pagination} aria-label="Пагинация">
                  <button
                    type="button"
                    className={styles.pageButton}
                    disabled={!skusData.previous || page <= 1}
                    onClick={() => goToPage(page - 1)}
                  >
                    ← Назад
                  </button>
                  <span className={styles.pageInfo}>Страница {page}</span>
                  <button
                    type="button"
                    className={styles.pageButton}
                    disabled={!skusData.next}
                    onClick={() => goToPage(page + 1)}
                  >
                    Вперёд →
                  </button>
                </nav>
              ) : null}
            </div>
          </>
        )}
      </div>
      </div>
    </div>
  );
}

function CategoryOverview({ category }: { category?: Category }) {
  const [openInst, setOpenInst] = useState(false);
  if (!category) return null;
  const hasDesc = Boolean(category.description?.trim());
  const hasInst = Boolean(category.instructions?.trim());
  if (!hasDesc && !hasInst) return null;

  return (
    <section className={styles.categoryOverview} aria-label="О категории">
      {hasDesc ? (
        <div className={styles.categoryDesc}>
          {parseProductDescription(category.description)
            .slice(0, 8)
            .map((block, index) => {
              if (block.type === "paragraph") {
                return (
                  <p key={`p-${index}`} className={styles.categoryLead}>
                    {softBreak(block.text)}
                  </p>
                );
              }
              if (block.type === "section") {
                const level = block.level ?? 3;
                const Tag = level === 2 ? "h2" : level === 4 ? "h4" : "h3";
                const className =
                  level === 2
                    ? styles.categoryDocTitle
                    : level === 4
                      ? styles.categorySubsection
                      : styles.categorySection;
                return (
                  <Tag key={`s-${index}`} className={className}>
                    {softBreak(block.title)}
                  </Tag>
                );
              }
              return (
                <ul key={`l-${index}`} className={styles.categoryList}>
                  {block.items.slice(0, 6).map((item) => (
                    <li key={item}>{softBreak(item)}</li>
                  ))}
                </ul>
              );
            })}
        </div>
      ) : null}
      {hasInst ? (
        <div className={styles.categoryInst}>
          <button
            type="button"
            className={styles.categoryInstToggle}
            aria-expanded={openInst}
            onClick={() => setOpenInst((v) => !v)}
          >
            {openInst ? "Скрыть инструкцию" : "Инструкция по монтажу и управлению"}
          </button>
          {openInst ? (
            <div className={styles.categoryInstBody}>
              <InstructionText
                text={category.instructions ?? ""}
                styles={{
                  lead: styles.categoryLead,
                  quote: styles.categoryQuote,
                  docTitle: styles.categoryDocTitle,
                  section: styles.categorySection,
                  subsection: styles.categorySubsection,
                  list: styles.categoryList,
                }}
              />
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
