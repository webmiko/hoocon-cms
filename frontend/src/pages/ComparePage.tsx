import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, type CompareResponse, type SKUList } from "../api/client";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { Seo } from "../components/Seo";
import { SignalSpecValue } from "../components/SignalSpecValue";
import { isModulatingSignalKey } from "../utils/isModulatingSignalKey";
import { ProtectedProductImage } from "../components/ProtectedProductImage";
import { useCompare } from "../compare/useCompare";
import {
  COMPARE_CAROUSEL_VISIBLE_COLS,
  COMPARE_MAX_SKUS,
  COMPARE_MIN_FOR_PAGE,
} from "../compare/constants";
import { parseCompareSlugsParam } from "../compare/storage";
import { useAsync } from "../hooks/useAsync";
import { softBreak } from "../utils/softBreak";
import { compactCardSpecName } from "../utils/cardHighlights";
import { catalogPathForSku } from "../utils/catalogPaths";
import { protectedContentHandlers } from "../utils/contentProtection";
import { productCardImageSrc } from "../utils/productImageSrc";
import styles from "./ComparePage.module.css";

interface CompareRowView {
  key: string;
  name: string;
  group: string;
  group_title: string;
  values: string[];
  diff: boolean;
  core?: boolean;
}

/**
 * Side-by-side SKU compare table (docs/plan-compare-sku.md этап 2).
 */
export function ComparePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { items, remove, clear, hydrateFromSlugs, enrichFromSkus, toggle } =
    useCompare();
  const [diffOnly, setDiffOnly] = useState(true);
  const [allSpecs, setAllSpecs] = useState(false);
  const [copied, setCopied] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [addQuery, setAddQuery] = useState("");
  const [addError, setAddError] = useState("");
  const dialogRef = useRef<HTMLDialogElement>(null);
  const carouselRef = useRef<HTMLDivElement>(null);
  const skuStripRef = useRef<HTMLDivElement>(null);
  const scrollSyncLock = useRef(false);
  const [carouselScroll, setCarouselScroll] = useState({ atStart: true, atEnd: true });

  const urlSlugs = useMemo(
    () => parseCompareSlugsParam(searchParams.get("skus")),
    [searchParams],
  );

  const slugs = urlSlugs.length > 0 ? urlSlugs : items.map((i) => i.slug);

  useEffect(() => {
    if (urlSlugs.length > 0) {
      hydrateFromSlugs(urlSlugs);
    }
  }, [urlSlugs, hydrateFromSlugs]);

  useEffect(() => {
    if (urlSlugs.length > 0) return;
    if (items.length === 0) return;
    setSearchParams(
      { skus: items.map((i) => i.slug).join(",") },
      { replace: true },
    );
  }, [urlSlugs.length, items, setSearchParams]);

  const { data, loading, error } = useAsync<CompareResponse>(
    () =>
      slugs.length > 0
        ? api.compare(slugs.slice(0, COMPARE_MAX_SKUS))
        : Promise.resolve({ skus: [], rows: [] }),
    slugs.join(","),
  );

  useEffect(() => {
    if (data?.skus?.length) {
      enrichFromSkus(data.skus);
    }
  }, [data, enrichFromSkus]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (addOpen && !dialog.open) {
      dialog.showModal();
    } else if (!addOpen && dialog.open) {
      dialog.close();
    }
  }, [addOpen]);

  const { data: searchData, loading: searchLoading } = useAsync(
    () =>
      addOpen
        ? api.skus({
            q: addQuery.trim(),
            page_size: "12",
          })
        : Promise.resolve({ results: [], count: 0 }),
    addOpen ? `add:${addQuery}` : "add:closed",
  );

  function syncSlugs(next: string[]) {
    if (next.length === 0) {
      setSearchParams({}, { replace: true });
      return;
    }
    setSearchParams({ skus: next.join(",") }, { replace: true });
  }

  function handleRemove(slug: string) {
    remove(slug);
    syncSlugs(slugs.filter((s) => s !== slug));
  }

  function handleClear() {
    clear();
    setSearchParams({}, { replace: true });
  }

  async function handleCopyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  function handleAddSku(sku: SKUList) {
    const result = toggle({
      slug: sku.slug,
      sku_code: sku.sku_code,
      name: sku.name,
      image: productCardImageSrc(sku.image),
    });
    if (result === "limit") {
      setAddError(`Можно сравнить не более ${COMPARE_MAX_SKUS} моделей.`);
      return;
    }
    setAddError("");
    const next =
      result === "added"
        ? [...slugs.filter((s) => s !== sku.slug), sku.slug]
        : slugs.filter((s) => s !== sku.slug);
    syncSlugs(next.slice(0, COMPARE_MAX_SKUS));
    if (result === "added" && next.length >= COMPARE_MAX_SKUS) {
      setAddOpen(false);
    }
  }

  const rows = useMemo(() => {
    let list = (data?.rows ?? []) as CompareRowView[];
    if (!allSpecs) {
      list = list.filter((row) => row.core !== false);
    }
    if (diffOnly) {
      list = list.filter((row) => row.diff);
    }
    return list;
  }, [data?.rows, allSpecs, diffOnly]);

  const groupedRows = useMemo(() => {
    if (!allSpecs) {
      return [{ key: "", title: "", rows }];
    }
    const groups: Array<{ key: string; title: string; rows: CompareRowView[] }> =
      [];
    const index = new Map<string, number>();
    for (const row of rows) {
      const key = row.group || "other";
      const title = row.group_title || "Прочие";
      let at = index.get(key);
      if (at === undefined) {
        at = groups.length;
        index.set(key, at);
        groups.push({ key, title, rows: [] });
      }
      groups[at]!.rows.push(row);
    }
    return groups;
  }, [rows, allSpecs]);

  const skus = data?.skus ?? [];
  const tooFew = slugs.length > 0 && slugs.length < COMPARE_MIN_FOR_PAGE;
  const canAddMore = slugs.length < COMPARE_MAX_SKUS;
  const showCarouselNav = skus.length > COMPARE_CAROUSEL_VISIBLE_COLS;

  const syncCarouselScroll = useCallback(() => {
    const el = carouselRef.current ?? skuStripRef.current;
    if (!el) {
      setCarouselScroll({ atStart: true, atEnd: true });
      return;
    }
    const maxScroll = el.scrollWidth - el.clientWidth;
    if (maxScroll <= 1) {
      setCarouselScroll({ atStart: true, atEnd: true });
      return;
    }
    setCarouselScroll({
      atStart: el.scrollLeft <= 1,
      atEnd: el.scrollLeft >= maxScroll - 1,
    });
  }, []);

  const syncHorizontalScroll = useCallback(
    (source: "strip" | "table") => {
      if (scrollSyncLock.current) return;
      const strip = skuStripRef.current;
      const table = carouselRef.current;
      if (!strip || !table) return;
      scrollSyncLock.current = true;
      const left = source === "strip" ? strip.scrollLeft : table.scrollLeft;
      if (source === "strip") {
        table.scrollLeft = left;
      } else {
        strip.scrollLeft = left;
      }
      syncCarouselScroll();
      window.requestAnimationFrame(() => {
        scrollSyncLock.current = false;
      });
    },
    [syncCarouselScroll],
  );

  const compareSlugsKey = slugs.join(",");

  useEffect(() => {
    const table = carouselRef.current;
    const strip = skuStripRef.current;
    if (table) table.scrollLeft = 0;
    if (strip) strip.scrollLeft = 0;
    syncCarouselScroll();
  }, [compareSlugsKey, syncCarouselScroll]);

  useEffect(() => {
    const table = carouselRef.current;
    const strip = skuStripRef.current;
    if (!table && !strip) return undefined;

    const onTableScroll = () => syncHorizontalScroll("table");
    const onStripScroll = () => syncHorizontalScroll("strip");
    table?.addEventListener("scroll", onTableScroll, { passive: true });
    strip?.addEventListener("scroll", onStripScroll, { passive: true });

    const ro = new ResizeObserver(() => syncCarouselScroll());
    if (table) ro.observe(table);
    if (strip) ro.observe(strip);

    return () => {
      table?.removeEventListener("scroll", onTableScroll);
      strip?.removeEventListener("scroll", onStripScroll);
      ro.disconnect();
    };
  }, [syncCarouselScroll, syncHorizontalScroll, skus.length]);

  function scrollCarousel(direction: -1 | 1) {
    const table = carouselRef.current;
    const strip = skuStripRef.current;
    const col =
      strip?.querySelector<HTMLElement>("[data-compare-col]")
      ?? table?.querySelector<HTMLElement>("[data-compare-col]");
    const step = col?.offsetWidth ?? 200;
    const current = table?.scrollLeft ?? strip?.scrollLeft ?? 0;
    const next = Math.max(0, current + direction * step);
    table?.scrollTo({ left: next, behavior: "smooth" });
    strip?.scrollTo({ left: next, behavior: "smooth" });
  }
  const rfqHref = `/rfq?skus=${encodeURIComponent(
    skus.map((s) => s.slug).join(","),
  )}`;

  const candidates = (searchData?.results ?? []).filter(
    (sku) => !slugs.includes(sku.slug),
  );

  return (
    <div className={styles.page}>
      <Seo
        title="Сравнение моделей"
        description={
          "Сравнение электроприводов и арматуры Hoocon по характеристикам: момент, " +
          "напряжение, управление и другие характеристики."
        }
        path="/compare"
        noindex
      />
      <Breadcrumbs
        items={[
          { label: "Каталог", to: "/catalog" },
          { label: "Сравнение" },
        ]}
      />

      <header className={styles.header}>
        <h1 className={styles.title}>Сравнение моделей</h1>
        <p className={styles.lead}>
          До {COMPARE_MAX_SKUS} моделей рядом. Отметьте товары в{" "}
          <Link to="/catalog">каталоге</Link> или на карточке товара.
        </p>
      </header>

      {slugs.length === 0 ? (
        <div className={styles.empty}>
          <p>Пока нечего сравнивать.</p>
          <Link to="/catalog" className={styles.emptyCta} data-brand-cta>
            Перейти в каталог
          </Link>
        </div>
      ) : null}

      {tooFew && !loading ? (
        <p className={styles.hint} role="status">
          Добавьте ещё хотя бы одну модель (сейчас {slugs.length} из{" "}
          {COMPARE_MIN_FOR_PAGE}–{COMPARE_MAX_SKUS}).
        </p>
      ) : null}

      {loading ? <p className={styles.loading}>Загрузка…</p> : null}
      {error ? (
        <p className={styles.error} role="alert">
          Не удалось загрузить сравнение. Проверьте ссылку или набор моделей.
        </p>
      ) : null}

      {skus.length >= COMPARE_MIN_FOR_PAGE ? (
        <>
          <div className={`${styles.toolbar} ${styles.noPrint}`}>
            <label className={styles.toggle}>
              <input
                type="checkbox"
                checked={diffOnly}
                onChange={(event) => setDiffOnly(event.target.checked)}
              />
              Только отличия
            </label>
            <label className={styles.toggle}>
              <input
                type="checkbox"
                checked={allSpecs}
                onChange={(event) => setAllSpecs(event.target.checked)}
              />
              Все характеристики
            </label>
            {canAddMore ? (
              <button
                type="button"
                className={styles.share}
                onClick={() => {
                  setAddError("");
                  setAddQuery("");
                  setAddOpen(true);
                }}
              >
                Добавить модель
              </button>
            ) : null}
            <Link to={rfqHref} className={styles.share}>
              Запросить КП по выбранным
            </Link>
            <button type="button" className={styles.clear} onClick={handleClear}>
              Очистить сравнение
            </button>
            <button
              type="button"
              className={styles.share}
              onClick={() => void handleCopyLink()}
            >
              {copied ? "Ссылка скопирована" : "Копировать ссылку"}
            </button>
          </div>

          <div className={`${styles.carouselWrap} ${styles.desktopOnly}`}>
            {showCarouselNav ? (
              <div className={`${styles.carouselNav} ${styles.noPrint}`}>
                <button
                  type="button"
                  className={styles.carouselBtn}
                  onClick={() => scrollCarousel(-1)}
                  disabled={carouselScroll.atStart}
                  aria-label="Предыдущие модели"
                >
                  ←
                </button>
                <span className={styles.carouselHint}>
                  {skus.length} моделей — прокрутите или листайте
                </span>
                <button
                  type="button"
                  className={styles.carouselBtn}
                  onClick={() => scrollCarousel(1)}
                  disabled={carouselScroll.atEnd}
                  aria-label="Следующие модели"
                >
                  →
                </button>
              </div>
            ) : null}
            <div
              className={`${styles.compareDesktop} u-protect-content`}
              {...protectedContentHandlers}
            >
              <div ref={skuStripRef} className={styles.skuHeadStrip}>
                <div className={styles.skuHeadGutter} aria-hidden="true" />
                {skus.map((sku) => (
                  <div
                    key={sku.slug}
                    className={styles.skuHeadCol}
                    data-compare-col=""
                  >
                    <CompareSkuHead
                      sku={sku}
                      onRemove={() => handleRemove(sku.slug)}
                    />
                  </div>
                ))}
              </div>
              <div ref={carouselRef} className={styles.scroll}>
                <table
                  className={styles.table}
                  style={
                    { "--compare-sku-cols": skus.length } as CSSProperties
                  }
                >
                  <thead>
                    <tr>
                      <th scope="col" className={styles.stickyCol}>
                        Характеристика
                      </th>
                      {skus.map((sku) => (
                        <th key={sku.slug} scope="col" className={styles.skuCol}>
                          <span className={`${styles.skuCode} text-tech`}>
                            {softBreak(sku.sku_code)}
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.length === 0 ? (
                      <tr>
                        <td colSpan={skus.length + 1} className={styles.noDiff}>
                          Все выбранные характеристики совпадают. Снимите
                          «Только отличия», чтобы увидеть полный список.
                        </td>
                      </tr>
                    ) : (
                      groupedRows.map((group) => (
                        <CompareGroupFragment
                          key={group.key || "core"}
                          group={group}
                          skus={skus}
                          showHeading={Boolean(allSpecs && group.title)}
                        />
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div
            className={`${styles.mobileCompare} ${styles.mobileOnly} u-protect-content`}
            {...protectedContentHandlers}
          >
            <CompareMobileProducts skus={skus} onRemove={handleRemove} />

            {rows.length === 0 ? (
              <p className={styles.noDiff} role="status">
                Все выбранные характеристики совпадают. Снимите «Только
                отличия», чтобы увидеть полный список.
              </p>
            ) : (
              <div className={styles.mobileSpecs}>
                {groupedRows.map((group) => (
                  <section
                    key={group.key || "core"}
                    className={styles.mobileGroup}
                    aria-label={
                      allSpecs && group.title ? group.title : undefined
                    }
                  >
                    {allSpecs && group.title ? (
                      <h2 className={styles.mobileGroupTitle}>{group.title}</h2>
                    ) : null}
                    {group.rows.map((row) => (
                      <article
                        key={row.key}
                        className={
                          row.diff
                            ? `${styles.mobileRow} ${styles.mobileDiff}`
                            : styles.mobileRow
                        }
                      >
                        <h3 className={styles.mobileAttr}>
                          {compactCardSpecName(row.name)}
                        </h3>
                        <dl className={styles.mobileValues}>
                          {row.values.map((value, index) => {
                            const sku = skus[index];
                            if (!sku) return null;
                            return (
                              <div
                                key={`${row.key}-${sku.slug}`}
                                className={styles.mobileValue}
                              >
                                <dt className={`${styles.skuCode} text-tech`}>
                                  {sku.sku_code}
                                </dt>
                                <dd>
                                  {isModulatingSignalKey(row.key) ? (
                                    <SignalSpecValue
                                      value={value}
                                      maInStock={Boolean(sku.in_stock_ma)}
                                    />
                                  ) : (
                                    softBreak(value)
                                  )}
                                </dd>
                              </div>
                            );
                          })}
                        </dl>
                      </article>
                    ))}
                  </section>
                ))}
              </div>
            )}
          </div>
        </>
      ) : null}

      <dialog
        ref={dialogRef}
        className={styles.addDialog}
        onClose={() => setAddOpen(false)}
        aria-labelledby="compare-add-title"
      >
        <div className={styles.addPanel}>
          <header className={styles.addHeader}>
            <h2 id="compare-add-title" className={styles.addTitle}>
              Добавить к сравнению
            </h2>
            <button
              type="button"
              className={styles.addClose}
              onClick={() => setAddOpen(false)}
              aria-label="Закрыть"
            >
              ×
            </button>
          </header>
          <label className={styles.addSearchLabel}>
            <span className={styles.srOnly}>Поиск модели</span>
            <input
              type="search"
              className={styles.addSearch}
              value={addQuery}
              onChange={(event) => setAddQuery(event.target.value)}
              placeholder="Артикул или название"
              autoFocus
            />
          </label>
          {addError ? (
            <p className={styles.error} role="alert">
              {addError}
            </p>
          ) : null}
          {searchLoading ? (
            <p className={styles.loading}>Поиск…</p>
          ) : (
            <ul className={styles.addList}>
              {candidates.length === 0 ? (
                <li className={styles.addEmpty}>Ничего не найдено</li>
              ) : (
                candidates.map((sku) => (
                  <li key={sku.slug}>
                    <button
                      type="button"
                      className={styles.addItem}
                      onClick={() => handleAddSku(sku)}
                    >
                      <span className={`${styles.skuCode} text-tech`}>
                        {sku.sku_code}
                      </span>
                      <span className={styles.addItemName}>{sku.name}</span>
                    </button>
                  </li>
                ))
              )}
            </ul>
          )}
        </div>
      </dialog>
    </div>
  );
}

function CompareMobileProducts({
  skus,
  onRemove,
}: {
  skus: SKUList[];
  onRemove: (slug: string) => void;
}) {
  const isCarousel = skus.length > COMPARE_CAROUSEL_VISIBLE_COLS;
  const trackRef = useRef<HTMLUListElement>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const currentIndex = Math.min(activeIndex, Math.max(0, skus.length - 1));

  useEffect(() => {
    const root = trackRef.current;
    if (!root || !isCarousel || skus.length === 0) return undefined;

    const updateActive = () => {
      const slides = Array.from(root.children) as HTMLElement[];
      if (slides.length === 0) return;
      const mid = root.scrollLeft + root.clientWidth / 2;
      let best = 0;
      let bestDist = Number.POSITIVE_INFINITY;
      slides.forEach((el, index) => {
        const center = el.offsetLeft + el.offsetWidth / 2;
        const dist = Math.abs(center - mid);
        if (dist < bestDist) {
          bestDist = dist;
          best = index;
        }
      });
      setActiveIndex(best);
    };

    let raf = 0;
    const scheduleUpdate = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        updateActive();
      });
    };

    updateActive();
    root.addEventListener("scroll", scheduleUpdate, { passive: true });
    const ro = new ResizeObserver(scheduleUpdate);
    ro.observe(root);
    return () => {
      if (raf) cancelAnimationFrame(raf);
      root.removeEventListener("scroll", scheduleUpdate);
      ro.disconnect();
    };
  }, [isCarousel, skus.length]);

  function scrollToIndex(index: number) {
    const root = trackRef.current;
    if (!root) return;
    const slide = root.children[index] as HTMLElement | undefined;
    if (!slide) return;
    root.scrollTo({ left: slide.offsetLeft, behavior: "smooth" });
  }

  function go(delta: -1 | 1) {
    scrollToIndex(Math.max(0, Math.min(skus.length - 1, currentIndex + delta)));
  }

  const listClass = isCarousel
    ? `${styles.mobileProducts} ${styles.mobileProductsCarousel}`
    : styles.mobileProducts;

  return (
    <div
      className={isCarousel ? styles.mobileCarousel : styles.mobileProductsBlock}
      role={isCarousel ? "region" : undefined}
      aria-roledescription={isCarousel ? "карусель" : undefined}
      aria-label={isCarousel ? "Выбранные модели" : undefined}
    >
      <ul ref={isCarousel ? trackRef : undefined} className={listClass}>
        {skus.map((sku) => (
          <li key={sku.slug} className={styles.mobileProduct}>
            <CompareSkuHead
              sku={sku}
              onRemove={() => onRemove(sku.slug)}
              compact
            />
          </li>
        ))}
      </ul>
      {isCarousel ? (
        <div className={styles.mobileCarouselControls}>
          <button
            type="button"
            className={styles.mobileCarouselBtn}
            onClick={() => go(-1)}
            disabled={currentIndex <= 0}
            aria-label="Предыдущая модель"
          >
            ←
          </button>
          <div
            className={styles.mobileCarouselDots}
            role="tablist"
            aria-label="Модели в сравнении"
          >
            {skus.map((sku, index) => (
              <button
                key={sku.slug}
                type="button"
                role="tab"
                aria-selected={index === currentIndex}
                aria-label={`${sku.sku_code}, ${index + 1} из ${skus.length}`}
                className={
                  index === currentIndex
                    ? `${styles.mobileCarouselDot} ${styles.mobileCarouselDotActive}`
                    : styles.mobileCarouselDot
                }
                onClick={() => scrollToIndex(index)}
              />
            ))}
          </div>
          <button
            type="button"
            className={styles.mobileCarouselBtn}
            onClick={() => go(1)}
            disabled={currentIndex >= skus.length - 1}
            aria-label="Следующая модель"
          >
            →
          </button>
        </div>
      ) : null}
    </div>
  );
}

function CompareSkuHead({
  sku,
  onRemove,
  compact = false,
}: {
  sku: SKUList;
  onRemove: () => void;
  compact?: boolean;
}) {
  const thumb = productCardImageSrc(sku.image);
  return (
    <div
      className={compact ? `${styles.skuHead} ${styles.skuHeadCompact}` : styles.skuHead}
    >
      <button
        type="button"
        className={`${styles.colRemove} ${styles.noPrint}`}
        onClick={onRemove}
        aria-label={`Убрать ${sku.sku_code}`}
      >
        ×
      </button>
      {thumb ? (
        <ProtectedProductImage
          src={thumb}
          alt=""
          frameClassName={styles.skuImage}
          className="u-protect-media"
          compact
          width={compact ? 56 : 72}
          height={compact ? 56 : 72}
          loading="lazy"
        />
      ) : (
        <span className={styles.skuImagePlaceholder} aria-hidden="true" />
      )}
      <Link to={catalogPathForSku(sku)} className={styles.skuLink}>
        <span className={`${styles.skuCode} text-tech`}>
          {softBreak(sku.sku_code)}
        </span>
        <span className={styles.skuName}>{softBreak(sku.name)}</span>
      </Link>
      <Link
        to={`${catalogPathForSku(sku)}#rfq`}
        className={`${styles.skuCta} ${styles.noPrint}`}
      >
        Запросить КП
      </Link>
    </div>
  );
}

function CompareGroupFragment({
  group,
  skus,
  showHeading,
}: {
  group: { key: string; title: string; rows: CompareRowView[] };
  skus: SKUList[];
  showHeading: boolean;
}) {
  return (
    <>
      {showHeading ? (
        <tr className={styles.groupRow}>
          <th scope="colgroup" colSpan={skus.length + 1}>
            {group.title}
          </th>
        </tr>
      ) : null}
      {group.rows.map((row) => (
        <tr key={row.key} className={row.diff ? styles.diffRow : undefined}>
          <th scope="row" className={styles.stickyCol}>
            {compactCardSpecName(row.name)}
          </th>
          {row.values.map((value, index) => (
            <td key={`${row.key}-${skus[index]?.slug ?? index}`}>
              {isModulatingSignalKey(row.key) ? (
                <SignalSpecValue
                  value={value}
                  maInStock={Boolean(skus[index]?.in_stock_ma)}
                />
              ) : (
                softBreak(value)
              )}
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
