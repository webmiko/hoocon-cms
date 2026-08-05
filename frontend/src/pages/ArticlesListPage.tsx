import { Link } from "react-router-dom";

import { Breadcrumbs } from "../components/Breadcrumbs";
import { Seo } from "../components/Seo";
import { ThemeAwareCover } from "../components/ThemeAwareCover";
import { api } from "../api/client";
import type { Article } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { buildBreadcrumbJsonLd } from "../utils/jsonLd";
import styles from "./ArticlesListPage.module.css";

/**
 * Articles index (/statyi) — OEM support-style knowledge list.
 * Spec: docs/readiness-backend-ux.md §4.3 (контент как у OEM, не lifestyle-блог).
 */
export function ArticlesListPage() {
  const { data, loading, error } = useAsync(() => api.articles());
  const articles: Article[] = data?.results ?? [];
  const [featured, ...rest] = articles;

  return (
    <div className={styles.page}>
      <Seo
        title="Статьи по электроприводам вентиляции и кондиционирования"
        description={
          "Подбор привода, монтаж, противопожарные и дымоудаляющие клапаны, " +
          "шаровые краны и замена аналогов Belimo — для инженеров и снабжения."
        }
        path="/statyi"
        jsonLd={[
          buildBreadcrumbJsonLd([
            { name: "Главная", path: "/" },
            { name: "Статьи", path: "/statyi" },
          ]),
        ]}
      />

      <Breadcrumbs
        items={[
          { label: "Главная", to: "/" },
          { label: "Статьи" },
        ]}
      />

      <header className={styles.header}>
        <p className={styles.eyebrow}>База знаний</p>
        <h1 className={styles.title}>
          Статьи по электроприводам вентиляции и кондиционирования
        </h1>
        <p className={styles.lead}>
          Практические материалы для инженеров и снабжения: подбор привода по
          характеристикам, монтаж, сравнение серий и замена аналогов Belimo.
        </p>
      </header>

      {loading && <p className={styles.status}>Загрузка…</p>}
      {error && (
        <p className={styles.status} role="alert">
          Не удалось загрузить статьи.
        </p>
      )}
      {!loading && !error && articles.length === 0 && (
        <p className={styles.status}>Пока нет опубликованных статей.</p>
      )}

      {featured ? (
        <article className={styles.featured}>
          <Link
            to={`/statyi/${featured.slug}`}
            className={styles.featuredLink}
          >
            <div className={styles.featuredMedia}>
              {featured.cover ? (
                <ThemeAwareCover
                  light={featured.cover}
                  dark={featured.cover_dark}
                  imgClassName={styles.featuredCover}
                  loading="eager"
                />
              ) : (
                <div className={styles.coverPlaceholder} aria-hidden />
              )}
            </div>
            <div className={styles.featuredBody}>
              <Meta article={featured} />
              <h2 className={styles.featuredTitle}>{featured.title}</h2>
              {featured.excerpt ? (
                <p className={styles.featuredExcerpt}>{featured.excerpt}</p>
              ) : null}
              <span className={styles.readMore}>Читать статью</span>
            </div>
          </Link>
        </article>
      ) : null}

      {rest.length > 0 ? (
        <ul className={styles.list}>
          {rest.map((article) => (
            <li key={article.id} className={styles.item}>
              <Link to={`/statyi/${article.slug}`} className={styles.itemLink}>
                <div className={styles.itemMedia}>
                  {article.cover ? (
                    <ThemeAwareCover
                      light={article.cover}
                      dark={article.cover_dark}
                      imgClassName={styles.itemCover}
                      loading="lazy"
                    />
                  ) : (
                    <div className={styles.coverPlaceholder} aria-hidden />
                  )}
                </div>
                <div className={styles.itemBody}>
                  <Meta article={article} />
                  <h2 className={styles.itemTitle}>{article.title}</h2>
                  {article.excerpt ? (
                    <p className={styles.itemExcerpt}>{article.excerpt}</p>
                  ) : null}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function Meta({ article }: { article: Article }) {
  const minutes = readingMinutes(article);
  return (
    <div className={styles.meta}>
      {article.published_at ? (
        <time dateTime={article.published_at}>
          {new Date(article.published_at).toLocaleDateString("ru-RU", {
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

function readingMinutes(article: Article): number {
  const raw = `${article.excerpt ?? ""} ${article.body ?? ""}`.replace(
    /<[^>]+>/g,
    " ",
  );
  const words = raw.trim().split(/\s+/).filter(Boolean).length;
  if (words < 40) return 0;
  return Math.max(1, Math.round(words / 180));
}
