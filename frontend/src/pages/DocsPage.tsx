import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, type DocsHubFile } from "../api/client";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { Seo } from "../components/Seo";
import { useAsync } from "../hooks/useAsync";
import { catalogSkuPath } from "../utils/catalogPaths";
import { buildBreadcrumbJsonLd } from "../utils/jsonLd";
import styles from "./DocsPage.module.css";

const SERIES_CHIPS = ["DA", "SA", "HV", "H81", "BR"] as const;

const KIND_CHIPS: Array<{ value: string; label: string }> = [
  { value: "manual", label: "Инструкции" },
  { value: "passport", label: "Паспорта" },
  { value: "certificate", label: "Сертификаты" },
  { value: "catalog", label: "Каталоги" },
  { value: "other", label: "Прочее" },
];

const KIND_LABEL: Record<string, string> = {
  manual: "Инструкция",
  passport: "Паспорт",
  certificate: "Сертификат",
  catalog: "Каталог",
  datasheet: "Документ",
  other: "Прочее",
};

function formatBytes(size: number): string {
  if (!size || size < 0) return "";
  if (size < 1024) return `${size} Б`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} КБ`;
  return `${(size / (1024 * 1024)).toFixed(1)} МБ`;
}

function groupFilesByFamily(
  files: DocsHubFile[],
): Array<{ family: string; series: string; files: DocsHubFile[] }> {
  const order: string[] = [];
  const map = new Map<string, { family: string; series: string; files: DocsHubFile[] }>();
  for (const file of files) {
    let group = map.get(file.family);
    if (!group) {
      group = { family: file.family, series: file.series, files: [] };
      map.set(file.family, group);
      order.push(file.family);
    }
    group.files.push(file);
  }
  return order.map((key) => map.get(key)!);
}

/**
 * Public download hub: search manuals/passports, download PDF or family ZIP.
 */
export function DocsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";
  const series = searchParams.get("series") ?? "";
  const kind = searchParams.get("kind") ?? "";
  const family = searchParams.get("family") ?? "";
  const listKey = `${q}\0${series}\0${kind}\0${family}`;

  const { data, loading, error } = useAsync(
    () =>
      api.docs({
        q: q || undefined,
        series: series || undefined,
        kind: kind || undefined,
        family: family || undefined,
      }),
    listKey,
  );

  const groups = useMemo(
    () => groupFilesByFamily(data?.files ?? []),
    [data?.files],
  );

  const zipByFamily = useMemo(() => {
    const map = new Map<string, string>();
    for (const item of data?.families ?? []) {
      map.set(item.key, item.zip_path);
    }
    return map;
  }, [data?.families]);

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    setSearchParams(next, { replace: true });
  }

  function toggleChip(
    param: "series" | "kind" | "family",
    value: string,
  ) {
    const current = searchParams.get(param) ?? "";
    updateParam(param, current === value ? "" : value);
  }

  function handleSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const value = (formData.get("q") as string | null)?.trim() ?? "";
    updateParam("q", value);
  }

  const jsonLd = [
    buildBreadcrumbJsonLd([
      { name: "Главная", path: "/" },
      { name: "Документация", path: "/dokumentaciya" },
    ]),
  ];

  return (
    <div className={styles.page}>
      <Seo
        title="Документация — инструкции и паспорта PDF"
        description={
          "Скачайте инструкции и паспорта изделий Hoocon: поиск по SKU и "
          + "семейству, PDF по одному файлу или архивом ZIP."
        }
        path="/dokumentaciya"
        jsonLd={jsonLd}
      />
      <Breadcrumbs
        items={[
          { label: "Главная", to: "/" },
          { label: "Документация" },
        ]}
      />

      <header className={styles.header}>
        <h1 className={styles.title}>Документация</h1>
        <p className={styles.lead}>
          Инструкции и паспорта изделий. Найдите модель или семейство и
          скачайте PDF — по одному файлу или архивом.
        </p>

        <form className={styles.form} onSubmit={handleSearch} role="search">
          <input
            type="search"
            name="q"
            defaultValue={q}
            key={q}
            className={styles.input}
            placeholder="SKU, семейство или название файла…"
            aria-label="Поиск по документации"
          />
          <button type="submit" className={styles.button} data-brand-fill>
            Найти
          </button>
        </form>

        <div className={styles.filters} aria-label="Фильтры">
          <div className={styles.chipRow}>
            <span className={styles.chipLabel}>Серия</span>
            {SERIES_CHIPS.map((value) => (
              <button
                key={value}
                type="button"
                className={
                  series === value ? styles.chipActive : styles.chip
                }
                aria-pressed={series === value}
                onClick={() => toggleChip("series", value)}
              >
                {value}
              </button>
            ))}
          </div>
          <div className={styles.chipRow}>
            <span className={styles.chipLabel}>Тип</span>
            {KIND_CHIPS.map((item) => (
              <button
                key={item.value}
                type="button"
                className={
                  kind === item.value ? styles.chipActive : styles.chip
                }
                aria-pressed={kind === item.value}
                onClick={() => toggleChip("kind", item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      {loading && <p className={styles.hint}>Загружаем документы…</p>}
      {error && (
        <p className={styles.error}>
          Не удалось загрузить список документов. Попробуйте позже.
        </p>
      )}

      {!loading && !error && groups.length === 0 && (
        <p className={styles.empty}>
          Ничего не найдено. Снимите фильтры или измените запрос.
        </p>
      )}

      {!loading && !error && groups.length > 0 && (
        <p className={styles.hint}>
          Найдено файлов: {data?.files.length ?? 0}
          {(data?.families.length ?? 0) > 0
            ? ` · семейств: ${data?.families.length ?? 0}`
            : ""}
        </p>
      )}

      <div className={styles.groups}>
        {groups.map((group) => {
          const zipPath = zipByFamily.get(group.family);
          return (
            <section
              key={group.family}
              className={styles.group}
              id={`family-${group.family}`}
            >
              <div className={styles.groupHead}>
                <div>
                  <h2 className={styles.groupTitle}>{group.family}</h2>
                  <p className={styles.groupMeta}>
                    {group.series} · {group.files.length}{" "}
                    {group.files.length === 1 ? "файл" : "файлов"}
                  </p>
                </div>
                {zipPath ? (
                  <a
                    className={styles.zipLink}
                    href={zipPath}
                    download={`${group.family}-docs.zip`}
                    data-brand-fill
                  >
                    Скачать ZIP
                  </a>
                ) : null}
              </div>
              <ul className={styles.fileList}>
                {group.files.map((file) => {
                  const skuHref =
                    file.category_slug && file.sku_slug
                      ? catalogSkuPath(file.category_slug, file.sku_slug)
                      : "";
                  return (
                    <li key={file.id} className={styles.fileItem}>
                      <a
                        href={file.file}
                        className={styles.fileLink}
                        download
                      >
                        <span className={styles.fileIcon}>PDF</span>
                        <span className={styles.fileBody}>
                          <span className={styles.fileTitle}>{file.title}</span>
                          <span className={styles.fileMeta}>
                            {KIND_LABEL[file.kind] ?? file.kind}
                            {file.size_bytes
                              ? ` · ${formatBytes(file.size_bytes)}`
                              : ""}
                          </span>
                        </span>
                      </a>
                      {file.kind === "passport" && skuHref ? (
                        <Link to={skuHref} className={styles.skuLink}>
                          {file.sku_code}
                        </Link>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}
