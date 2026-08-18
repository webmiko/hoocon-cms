import { Link, useSearchParams } from "react-router-dom";

import { Breadcrumbs } from "../components/Breadcrumbs";
import { Seo } from "../components/Seo";
import { api } from "../api/client";
import type { News, NewsCategory } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { generatedCoverCaption } from "../utils/generatedCoverCaption";
import { buildBreadcrumbJsonLd } from "../utils/jsonLd";
import { stripHtmlToText } from "../utils/stripHtml";
import styles from "./NewsListPage.module.css";

type Ordering = "newest" | "oldest";

/**
 * News index (/novosti) — same layout language as articles list.
 * Spec: docs/readiness-backend-ux.md §4.3.
 *
 * URL: ``?category=<slug>&ordering=newest|oldest``.
 */
export function NewsListPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const category = (searchParams.get("category") || "").trim();
  const ordering: Ordering =
    searchParams.get("ordering") === "oldest" ? "oldest" : "newest";

  const { data: categories } = useAsync(() => api.newsCategories(), "cats");
  const listKey = `${category}|${ordering}`;
  const { data, loading, error } = useAsync(
    () =>
      api.news({
        category: category || undefined,
        ordering,
      }),
    listKey,
  );
  const items: News[] = data?.results ?? [];
  const [featured, ...rest] = items;
  const featuredExcerpt = featured ? excerptOf(featured) : "";
  const featuredCoverCaption = featured ? generatedCoverCaption("news", featured.slug) : null;
  const rubrics: NewsCategory[] = categories ?? [];

  function patchParams(next: { category?: string; ordering?: Ordering }) {
    const params = new URLSearchParams(searchParams);
    const cat = next.category !== undefined ? next.category : category;
    const ord = next.ordering !== undefined ? next.ordering : ordering;
    if (cat) params.set("category", cat);
    else params.delete("category");
    if (ord === "oldest") params.set("ordering", "oldest");
    else params.delete("ordering");
    setSearchParams(params, { replace: true });
  }

  return (
    <div className={styles.page}>
      <Seo
        title="Новости Hoocon"
        description={
          "Новости производства и каталога электроприводов Hoocon: выставки, " +
          "цены, партнёрские анонсы."
        }
        path="/novosti"
        jsonLd={[
          buildBreadcrumbJsonLd([
            { name: "Главная", path: "/" },
            { name: "Новости", path: "/novosti" },
          ]),
        ]}
      />

      <Breadcrumbs
        items={[
          { label: "Главная", to: "/" },
          { label: "Новости" },
        ]}
      />

      <header className={styles.header}>
        <p className={styles.eyebrow}>Компания</p>
        <h1 className={styles.title}>Новости</h1>
        <p className={styles.lead}>
          Анонсы выставок, обновления условий поставок и заметки для партнёров
          и снабжения.
        </p>
      </header>

      <div className={styles.filters} role="toolbar" aria-label="Фильтр новостей">
        <div className={styles.chips} role="group" aria-label="Категории">
          <button
            type="button"
            className={`${styles.chip}${!category ? ` ${styles.chipActive}` : ""}`}
            aria-pressed={!category}
            onClick={() => patchParams({ category: "" })}
          >
            Все
          </button>
          {rubrics.map((rubric) => {
            const active = category === rubric.slug;
            return (
              <button
                key={rubric.slug}
                type="button"
                className={`${styles.chip}${active ? ` ${styles.chipActive}` : ""}`}
                aria-pressed={active}
                onClick={() => patchParams({ category: rubric.slug })}
              >
                {rubric.name}
              </button>
            );
          })}
        </div>
        <label className={styles.sort}>
          <span className={styles.sortLabel}>Сортировка</span>
          <select
            className={styles.sortSelect}
            value={ordering}
            onChange={(event) =>
              patchParams({
                ordering: event.target.value === "oldest" ? "oldest" : "newest",
              })
            }
          >
            <option value="newest">Сначала новые</option>
            <option value="oldest">Сначала старые</option>
          </select>
        </label>
      </div>

      {loading && <p className={styles.status}>Загрузка…</p>}
      {error && (
        <p className={styles.status} role="alert">
          Не удалось загрузить новости.
        </p>
      )}
      {!loading && !error && items.length === 0 && (
        <p className={styles.status}>Пока нет опубликованных новостей.</p>
      )}

      {featured ? (
        <article className={styles.featured}>
          <Link to={`/novosti/${featured.slug}`} className={styles.featuredLink}>
            <div className={styles.featuredMedia}>
              {featured.cover ? (
                <img
                  className={
                    featuredCoverCaption
                      ? `${styles.featuredCover} ${styles.coverGenerated}`
                      : styles.featuredCover
                  }
                  src={featured.cover}
                  alt=""
                  loading="eager"
                />
              ) : (
                <div className={styles.coverPlaceholder} aria-hidden />
              )}
              {featuredCoverCaption ? (
                <span className={styles.coverNote}>{featuredCoverCaption}</span>
              ) : null}
            </div>
            <div className={styles.featuredBody}>
              <Meta item={featured} />
              <h2 className={styles.featuredTitle}>{featured.title}</h2>
              {featuredExcerpt ? (
                <p className={styles.featuredExcerpt}>{featuredExcerpt}</p>
              ) : null}
              <span className={styles.readMore}>Читать новость</span>
            </div>
          </Link>
        </article>
      ) : null}

      {rest.length > 0 ? (
        <ul className={styles.list}>
          {rest.map((item) => {
            const excerpt = excerptOf(item);
            const coverNote = generatedCoverCaption("news", item.slug);
            return (
              <li key={item.id} className={styles.item}>
                <Link to={`/novosti/${item.slug}`} className={styles.itemLink}>
                  <div className={styles.itemMedia}>
                    {item.cover ? (
                      <img
                        className={
                          coverNote
                            ? `${styles.itemCover} ${styles.coverGenerated}`
                            : styles.itemCover
                        }
                        src={item.cover}
                        alt=""
                        loading="lazy"
                      />
                    ) : (
                      <div className={styles.coverPlaceholder} aria-hidden />
                    )}
                    {coverNote ? <span className={styles.coverNote}>{coverNote}</span> : null}
                  </div>
                  <div className={styles.itemBody}>
                    <Meta item={item} />
                    <h2 className={styles.itemTitle}>{item.title}</h2>
                    {excerpt ? (
                      <p className={styles.itemExcerpt}>{excerpt}</p>
                    ) : null}
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

function Meta({ item }: { item: News }) {
  const minutes = readingMinutes(item);
  return (
    <div className={styles.meta}>
      {item.category ? (
        <span className={styles.badge}>{item.category.name}</span>
      ) : null}
      {item.published_at ? (
        <time dateTime={item.published_at}>
          {new Date(item.published_at).toLocaleDateString("ru-RU", {
            year: "numeric",
            month: "long",
            day: "numeric",
          })}
        </time>
      ) : null}
      {minutes > 0 ? (
        <span className={styles.metaSep} aria-hidden>
          ·
        </span>
      ) : null}
      {minutes > 0 ? <span>{minutes} мин чтения</span> : null}
    </div>
  );
}

function excerptOf(item: News): string {
  const plain = stripHtmlToText(item.body ?? "");
  if (!plain) return "";
  if (plain.length <= 180) return plain;
  const cut = plain.slice(0, 179);
  const spaced = cut.includes(" ") ? cut.slice(0, cut.lastIndexOf(" ")) : cut;
  return `${spaced}…`;
}

function readingMinutes(item: News): number {
  const words = stripHtmlToText(item.body ?? "").split(/\s+/).filter(Boolean).length;
  if (words < 40) return 0;
  return Math.max(1, Math.round(words / 180));
}
