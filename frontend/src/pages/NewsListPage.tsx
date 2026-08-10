import { Link } from "react-router-dom";

import { Breadcrumbs } from "../components/Breadcrumbs";
import { Seo } from "../components/Seo";
import { api } from "../api/client";
import type { News } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { buildBreadcrumbJsonLd } from "../utils/jsonLd";
import { stripHtmlToText } from "../utils/stripHtml";
import styles from "./NewsListPage.module.css";

/**
 * News index (/novosti) — same layout language as articles list.
 * Spec: docs/readiness-backend-ux.md §4.3.
 */
export function NewsListPage() {
  const { data, loading, error } = useAsync(() => api.news());
  const items: News[] = data?.results ?? [];
  const [featured, ...rest] = items;
  const featuredExcerpt = featured ? excerptOf(featured) : "";

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
                  className={styles.featuredCover}
                  src={featured.cover}
                  alt=""
                  loading="eager"
                />
              ) : (
                <div className={styles.coverPlaceholder} aria-hidden />
              )}
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
            return (
              <li key={item.id} className={styles.item}>
                <Link to={`/novosti/${item.slug}`} className={styles.itemLink}>
                  <div className={styles.itemMedia}>
                    {item.cover ? (
                      <img
                        className={styles.itemCover}
                        src={item.cover}
                        alt=""
                        loading="lazy"
                      />
                    ) : (
                      <div className={styles.coverPlaceholder} aria-hidden />
                    )}
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
