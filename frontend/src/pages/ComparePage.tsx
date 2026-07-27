import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, type CompareResponse, type SKUList } from "../api/client";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { Seo } from "../components/Seo";
import { SignalSpecValue } from "../components/SignalSpecValue";
import { isModulatingSignalKey } from "../utils/isModulatingSignalKey";
import { ProtectedProductImage } from "../components/ProtectedProductImage";
import { useCompare } from "../compare/useCompare";
import {
  COMPARE_MAX_SKUS,
  COMPARE_MIN_FOR_PAGE,
} from "../compare/constants";
import { parseCompareSlugsParam } from "../compare/storage";
import { useAsync } from "../hooks/useAsync";
import { softBreak } from "../utils/softBreak";
import { compactCardSpecName } from "../utils/cardHighlights";
import { catalogPathForSku } from "../utils/catalogPaths";
import { protectedContentHandlers } from "../utils/contentProtection";
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
      image: sku.image?.image ?? null,
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
  const rfqHref = `/consultation?skus=${encodeURIComponent(
    skus.map((s) => s.sku_code).join(","),
  )}`;

  const candidates = (searchData?.results ?? []).filter(
    (sku) => !slugs.includes(sku.slug),
  );

  return (
    <div className={styles.page}>
      <Seo
        title="Сравнение моделей"
        description={
          "Сравнение электроприводов и арматуры Hoocon по ТТХ: момент, " +
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
          <Link to="/catalog" className={styles.emptyCta} data-on-dark-cta>
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

          <div
            className={`${styles.scroll} u-protect-content`}
            {...protectedContentHandlers}
          >
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col" className={styles.stickyCol}>
                    Характеристика
                  </th>
                  {skus.map((sku) => (
                    <th key={sku.slug} scope="col" className={styles.skuCol}>
                      <div className={styles.skuHead}>
                        <button
                          type="button"
                          className={`${styles.colRemove} ${styles.noPrint}`}
                          onClick={() => handleRemove(sku.slug)}
                          aria-label={`Убрать ${sku.sku_code}`}
                        >
                          ×
                        </button>
                        {sku.image?.image ? (
                          <ProtectedProductImage
                            src={sku.image.image}
                            alt=""
                            className={`${styles.skuImage} u-protect-media`}
                            width={72}
                            height={72}
                            loading="lazy"
                          />
                        ) : (
                          <span
                            className={styles.skuImagePlaceholder}
                            aria-hidden="true"
                          />
                        )}
                        <Link
                          to={catalogPathForSku(sku)}
                          className={styles.skuLink}
                        >
                          <span className={`${styles.skuCode} text-tech`}>
                            {softBreak(sku.sku_code)}
                          </span>
                          <span className={styles.skuName}>
                            {softBreak(sku.name)}
                          </span>
                        </Link>
                        <Link
                          to={`${catalogPathForSku(sku)}#rfq`}
                          className={`${styles.skuCta} ${styles.noPrint}`}
                        >
                          Запросить цену
                        </Link>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={skus.length + 1} className={styles.noDiff}>
                      Все выбранные характеристики совпадают. Снимите «Только
                      отличия», чтобы увидеть полный список.
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
                <SignalSpecValue value={value} />
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
