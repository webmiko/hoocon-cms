import { Link, useSearchParams } from "react-router-dom";
import { useMemo, useState } from "react";

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
import { parseDescription } from "../utils/parseDescription";
import {
  isModulatingSignalKey,
  SignalSpecValue,
} from "../components/SignalSpecValue";
import { CompareToggle } from "../components/CompareToggle";
import { SoftBreakText } from "../components/SoftBreakText";
import { softBreak } from "../utils/softBreak";
import { specDisplayUnit } from "../utils/specDisplay";
import styles from "./CatalogPage.module.css";

/** Facet query keys synced to the URL (backend catalog.facets). */
const FACET_KEYS = [
  "moment",
  "voltage",
  "control",
  "area",
  "aux_switch",
  "dn",
  "ways",
  "kvs",
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
 * Filters sync to query string so URLs are shareable.
 * Spec: docs/plan-detail-mvp.md S2; live PDP hero style (hoocon.ru).
 */
export function CatalogPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const category = searchParams.get("category") ?? "";
  const q = searchParams.get("q") ?? "";
  const page = parseInt(searchParams.get("page") ?? "1", 10) || 1;

  const activeFacets: Partial<Record<FacetKey, string>> = {};
  for (const key of FACET_KEYS) {
    const value = searchParams.get(key);
    if (value) activeFacets[key] = value;
  }

  const { data: categoriesData } = useAsync(() => api.categories(), []);
  const { data: facetsData } = useAsync(
    () => api.facets(category ? { category } : undefined),
    [category],
  );

  const params: Record<string, string> = {};
  if (category) params.category = category;
  if (q) params.q = q;
  if (page > 1) params.page = String(page);
  for (const [key, value] of Object.entries(activeFacets)) {
    if (value) params[key] = value;
  }

  const facetKey = FACET_KEYS.map((k) => activeFacets[k] ?? "").join("|");
  const listKey = `${category}|${q}|${page}|${facetKey}`;
  const { data: skusData, loading, error } = useAsync(
    () => api.skus(params),
    [category, q, page, facetKey],
  );

  const categories: Category[] = categoriesData?.results ?? [];
  const facets: CatalogFacet[] = facetsData?.results ?? [];
  const activeCount =
    Object.keys(activeFacets).length + (q ? 1 : 0) + (category ? 1 : 0);
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
    if (extras.length === 0) return base;
    const seen = new Set(base.map((s) => s.slug));
    const out = [...base];
    for (const sku of extras) {
      if (seen.has(sku.slug)) continue;
      seen.add(sku.slug);
      out.push(sku);
    }
    return out;
  }, [skusData?.results, append, listKey]);

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
            onClick={() => updateFilter("category", "")}
          >
            <span className={styles.optionText}>Все категории</span>
          </Link>
          {categories.map((cat) => (
            <Link
              key={cat.slug}
              to={`/catalog?category=${encodeURIComponent(cat.slug)}`}
              className={
                category === cat.slug ? styles.optionRowActive : styles.optionRow
              }
              onClick={() => updateFilter("category", cat.slug)}
            >
              <span className={styles.optionText}>{softBreak(cat.name)}</span>
            </Link>
          ))}
        </nav>
      </details>

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
        title="Каталог электроприводов ОВК"
        description="Каталог электроприводов Hoocon для вентиляции и кондиционирования. Фильтры по моменту, напряжению, типу; паспорта PDF; подбор аналогов Belimo."
        path="/catalog"
        jsonLd={[
          buildBreadcrumbJsonLd([
            { name: "Главная", path: "/" },
            { name: "Каталог", path: "/catalog" },
            ...(activeCategory
              ? [
                  {
                    name: activeCategory.name,
                    path: `/catalog?category=${encodeURIComponent(activeCategory.slug)}`,
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
                onClick={() => updateFilter("category", "")}
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

        {loading && <CatalogSkeleton />}
        {error && (
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
            <div className={styles.grid}>
              {displayedSkus.map((sku) => (
                <article key={sku.slug} className={styles.card}>
                  <Link
                    to={`/${sku.slug}`}
                    className={styles.cardHit}
                    aria-label={sku.name}
                  />
                  {sku.image?.image ? (
                    <div className={styles.cardMedia}>
                      <CompareToggle
                        className={`${styles.cardCompare} ${styles.cardInteractive}`}
                        item={{
                          slug: sku.slug,
                          sku_code: sku.sku_code,
                          name: sku.name,
                          image: sku.image.image,
                        }}
                      />
                      <img
                        src={sku.image.image}
                        alt={sku.image.alt || sku.name}
                        className={styles.cardImage}
                        loading="lazy"
                        decoding="async"
                      />
                    </div>
                  ) : (
                    <div className={styles.cardMediaPlaceholder}>
                      <CompareToggle
                        className={`${styles.cardCompare} ${styles.cardInteractive}`}
                        item={{
                          slug: sku.slug,
                          sku_code: sku.sku_code,
                          name: sku.name,
                          image: null,
                        }}
                      />
                    </div>
                  )}
                  <div className={styles.cardBody}>
                    <p className={`${styles.cardCode} text-tech`}>
                      {softBreak(sku.sku_code)}
                    </p>
                    <h3 className={styles.cardTitle}>{softBreak(sku.name)}</h3>
                    {sku.highlights && sku.highlights.length > 0 ? (
                      <ul className={styles.cardSpecs}>
                        {sku.highlights.slice(0, 6).map((h) => {
                          const unit = specDisplayUnit(h.value, h.unit);
                          return (
                            <li key={h.key}>
                              <span className={styles.cardSpecName}>
                                {h.name}
                              </span>
                              {isModulatingSignalKey(h.key) ? (
                                <SignalSpecValue
                                  value={`${h.value}${unit ? ` ${unit}` : ""}`}
                                  className={`${styles.cardSpecValue} ${styles.cardInteractive}`}
                                />
                              ) : (
                                <span className={styles.cardSpecValue}>
                                  <SoftBreakText text={h.value} />
                                  {unit ? ` ${unit}` : ""}
                                </span>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    ) : null}
                    <div className={styles.cardFooter}>
                      {sku.analog_belimo_code ? (
                        <span className={`${styles.cardAnalog} text-tech`}>
                          Belimo: {softBreak(sku.analog_belimo_code)}
                        </span>
                      ) : (
                        <span className={styles.cardPriceOnRequest}>
                          Цена по запросу
                        </span>
                      )}
                      <span className={styles.cardCta}>Паспорт и ТТХ</span>
                    </div>
                  </div>
                </article>
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
          {parseDescription(category.description)
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
                return (
                  <h3 key={`s-${index}`} className={styles.categorySection}>
                    {softBreak(block.title)}
                  </h3>
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
              {parseDescription(category.instructions).map((block, index) => {
                if (block.type === "paragraph") {
                  return (
                    <p key={`ip-${index}`} className={styles.categoryLead}>
                      {softBreak(block.text)}
                    </p>
                  );
                }
                if (block.type === "section") {
                  return (
                    <h3 key={`is-${index}`} className={styles.categorySection}>
                      {softBreak(block.title)}
                    </h3>
                  );
                }
                return (
                  <ul key={`il-${index}`} className={styles.categoryList}>
                    {block.items.map((item) => (
                      <li key={item}>{softBreak(item)}</li>
                    ))}
                  </ul>
                );
              })}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
