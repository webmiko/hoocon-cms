import { Link, useParams } from "react-router-dom";

import { RelatedArticlesCarousel } from "../components/RelatedArticlesCarousel";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { Seo } from "../components/Seo";
import { api } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { sanitizeHtml } from "../utils/sanitize";
import { stripHtmlToText } from "../utils/stripHtml";
import {
  buildArticleJsonLd,
  buildBreadcrumbJsonLd,
} from "../utils/jsonLd";
import { metaDescription } from "../utils/seoMeta";
import styles from "./NewsPage.module.css";
import "../styles/cms-body-charts.css";

/**
 * News detail — same reading layout as articles.
 * Spec: ПЛАН §6 Iter 4; docs/readiness-backend-ux.md §4.3.
 */
export function NewsPage() {
  const { slug } = useParams<{ slug: string }>();
  const { data: news, loading, error } = useAsync(
    () => api.newsDetail(slug!),
    slug,
  );
  const { data: listData } = useAsync(() => api.news());

  if (loading) {
    return <p className={styles.status}>Загрузка…</p>;
  }

  if (error || !news) {
    return (
      <div className={styles.notFound}>
        <h1>Новость не найдена</h1>
        <Link to="/novosti" className={styles.link}>
          ← Все новости
        </Link>
      </div>
    );
  }

  const plain = stripHtmlToText(news.body);
  const description = metaDescription(plain);
  const minutes = readingMinutes(news.body);
  const related = (listData?.results ?? [])
    .filter((item) => item.slug !== news.slug)
    .slice(0, 8);

  return (
    <div className={styles.page}>
      <article className={styles.article}>
        <Seo
          title={news.title}
          description={description}
          path={`/novosti/${news.slug}`}
          ogType="article"
          image={news.cover}
          jsonLd={[
            buildArticleJsonLd({
              title: news.title,
              slug: news.slug,
              description,
              published_at: news.published_at,
              pathPrefix: "/novosti",
            }),
            buildBreadcrumbJsonLd([
              { name: "Главная", path: "/" },
              { name: "Новости", path: "/novosti" },
              { name: news.title, path: `/novosti/${news.slug}` },
            ]),
          ]}
        />
        <Breadcrumbs
          items={[
            { label: "Главная", to: "/" },
            { label: "Новости", to: "/novosti" },
            { label: news.title },
          ]}
        />

        <header className={styles.header}>
          <p className={styles.eyebrow}>Новость</p>
          <h1 className={styles.title}>{news.title}</h1>
          <div className={styles.meta}>
            {news.category ? (
              <span className={styles.badge}>{news.category.name}</span>
            ) : null}
            {news.published_at ? (
              <time dateTime={news.published_at}>
                {new Date(news.published_at).toLocaleDateString("ru-RU", {
                  year: "numeric",
                  month: "long",
                  day: "numeric",
                })}
              </time>
            ) : null}
            {minutes > 0 ? (
              <>
                <span className={styles.metaSep} aria-hidden>
                  ·
                </span>
                <span>{minutes} мин чтения</span>
              </>
            ) : null}
          </div>
        </header>

        {news.cover ? (
          <figure className={styles.coverFigure}>
            <img
              className={styles.cover}
              src={news.cover}
              alt={news.title}
            />
          </figure>
        ) : null}

        <div
          className={`${styles.body} cms-rich-body`}
          dangerouslySetInnerHTML={{ __html: sanitizeHtml(news.body) }}
        />

        <aside className={styles.cta} aria-labelledby="news-cta-heading">
          <h2 id="news-cta-heading" className={styles.ctaTitle}>
            Нужен подбор привода?
          </h2>
          <p className={styles.ctaText}>
            Инженер поможет подобрать модель по характеристикам, крутящему моменту и сигналу
            управления.
          </p>
          <Link to="/consultation" className={styles.ctaLink}>
            Консультация инженера →
          </Link>
        </aside>

        <footer className={styles.footer}>
          <Link to="/novosti" className={styles.backLink}>
            ← Все новости
          </Link>
        </footer>
      </article>

      {related.length > 0 ? (
        <section className={styles.related} aria-labelledby="related-news-heading">
          <h2 id="related-news-heading" className={styles.relatedTitle}>
            Другие новости
          </h2>
          <RelatedArticlesCarousel
            articles={related}
            pathPrefix="/novosti"
            navLabel="новости"
          />
        </section>
      ) : null}
    </div>
  );
}

function readingMinutes(html: string): number {
  const words = stripHtmlToText(html).split(/\s+/).filter(Boolean).length;
  if (words < 40) return 0;
  return Math.max(1, Math.round(words / 180));
}
