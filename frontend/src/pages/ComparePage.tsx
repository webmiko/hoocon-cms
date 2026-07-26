import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, type CompareResponse } from "../api/client";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { Seo } from "../components/Seo";
import {
  isModulatingSignalKey,
  SignalSpecValue,
} from "../components/SignalSpecValue";
import { ProtectedProductImage } from "../components/ProtectedProductImage";
import { useCompare } from "../compare/CompareContext";
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

/**
 * Side-by-side SKU compare table (docs/plan-compare-sku.md).
 */
export function ComparePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { items, remove, clear, hydrateFromSlugs, enrichFromSkus } =
    useCompare();
  const [diffOnly, setDiffOnly] = useState(true);
  const [copied, setCopied] = useState(false);

  const urlSlugs = useMemo(
    () => parseCompareSlugsParam(searchParams.get("skus")),
    [searchParams],
  );

  // URL wins when present; otherwise tray items drive the page.
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
    [slugs.join(",")],
  );

  useEffect(() => {
    if (data?.skus?.length) {
      enrichFromSkus(data.skus);
    }
  }, [data, enrichFromSkus]);

  function handleRemove(slug: string) {
    remove(slug);
    const next = slugs.filter((s) => s !== slug);
    if (next.length === 0) {
      setSearchParams({}, { replace: true });
      return;
    }
    setSearchParams({ skus: next.join(",") }, { replace: true });
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

  const rows = useMemo(() => {
    const all = data?.rows ?? [];
    if (!diffOnly) return all;
    return all.filter((row) => row.diff);
  }, [data, diffOnly]);

  const skus = data?.skus ?? [];
  const tooFew = slugs.length > 0 && slugs.length < COMPARE_MIN_FOR_PAGE;

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
          <div className={styles.toolbar}>
            <label className={styles.toggle}>
              <input
                type="checkbox"
                checked={diffOnly}
                onChange={(event) => setDiffOnly(event.target.checked)}
              />
              Только отличия
            </label>
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
                          className={styles.colRemove}
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
                          className={styles.skuCta}
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
                  rows.map((row) => (
                    <tr
                      key={row.key}
                      className={row.diff ? styles.diffRow : undefined}
                    >
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
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </div>
  );
}
