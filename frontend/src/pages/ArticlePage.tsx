import { Link, useParams } from "react-router-dom";

import { RelatedArticlesCarousel } from "../components/RelatedArticlesCarousel";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { ProtectedProductImage } from "../components/ProtectedProductImage";
import { Seo } from "../components/Seo";
import { api } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { sanitizeHtml } from "../utils/sanitize";
import { stripHtmlToText } from "../utils/stripHtml";
import {
  buildArticleJsonLd,
  buildBreadcrumbJsonLd,
} from "../utils/jsonLd";
import { catalogPathForSku } from "../utils/catalogPaths";
import { protectedContentHandlers } from "../utils/contentProtection";
import styles from "./ArticlePage.module.css";
import "../styles/cms-body-charts.css";

/**
 * Article detail — readable column, scannable hierarchy, related links.
 * Spec: readiness §4.3 OEM support; WCAG reading comfort (65–75ch, 1.7 lh).
 */
export function ArticlePage() {
  const { slug } = useParams<{ slug: string }>();
  const { data: article, loading, error } = useAsync(
    () => api.articleDetail(slug!),
    [slug],
  );
  const { data: listData } = useAsync(() => api.articles(), []);

  if (loading) {
    return <p className={styles.status}>Загрузка…</p>;
  }

  if (error || !article) {
    return (
      <div className={styles.notFound}>
        <h1>Статья не найдена</h1>
        <Link to="/statyi" className={styles.link}>
          ← Все статьи
        </Link>
      </div>
    );
  }

  const plain = stripHtmlToText(article.excerpt || article.body);
  const minutes = readingMinutes(article.body);
  const related = (listData?.results ?? [])
    .filter((item) => item.slug !== article.slug)
    .slice(0, 8);

  return (
    <div className={styles.page}>
      <article className={styles.article}>
        <Seo
          title={article.title}
          description={plain.slice(0, 160)}
          path={`/statyi/${article.slug}`}
          ogType="article"
          jsonLd={[
            buildArticleJsonLd({
              title: article.title,
              slug: article.slug,
              description: plain.slice(0, 160),
              published_at: article.published_at,
              pathPrefix: "/statyi",
            }),
            buildBreadcrumbJsonLd([
              { name: "Главная", path: "/" },
              { name: "Статьи", path: "/statyi" },
              { name: article.title, path: `/statyi/${article.slug}` },
            ]),
          ]}
        />
        <Breadcrumbs
          items={[
            { label: "Главная", to: "/" },
            { label: "Статьи", to: "/statyi" },
            { label: article.title },
          ]}
        />

        <header className={styles.header}>
          <p className={styles.eyebrow}>Статья</p>
          <h1 className={styles.title}>{article.title}</h1>
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
              <>
                <span className={styles.metaSep} aria-hidden>
                  ·
                </span>
                <span>{minutes} мин чтения</span>
              </>
            ) : null}
          </div>
          {article.excerpt ? (
            <p className={styles.dek}>{article.excerpt}</p>
          ) : null}
        </header>

        {article.cover ? (
          <figure className={styles.coverFigure}>
            <img className={styles.cover} src={article.cover} alt="" />
          </figure>
        ) : null}

        {/* Body HTML from CMS; DOMPurify — security-baseline §3.6 */}
        <div
          className={`${styles.body} cms-rich-body`}
          dangerouslySetInnerHTML={{ __html: sanitizeHtml(article.body) }}
        />

        {article.related_skus && article.related_skus.length > 0 ? (
          <section
            className={`${styles.products} u-protect-content`}
            aria-labelledby="article-products-heading"
            {...protectedContentHandlers}
          >
            <h2 id="article-products-heading" className={styles.productsTitle}>
              Упомянутые товары
            </h2>
            <ul className={styles.productsList}>
              {article.related_skus.map((sku) => (
                <li key={sku.slug}>
                  <Link
                    to={catalogPathForSku(sku)}
                    className={styles.productLink}
                  >
                    {sku.image ? (
                      <ProtectedProductImage
                        className={`${styles.productImage} u-protect-media`}
                        src={sku.image}
                        alt=""
                        loading="lazy"
                      />
                    ) : (
                      <div className={styles.productImagePh} aria-hidden />
                    )}
                    <span className={styles.productCode}>{sku.sku_code}</span>
                    <span className={styles.productName}>{sku.name}</span>
                  </Link>
                </li>
              ))}
            </ul>
            <Link to="/catalog" className={styles.productsCatalog}>
              Весь каталог →
            </Link>
          </section>
        ) : null}

        <aside className={styles.cta} aria-labelledby="article-cta-heading">
          <h2 id="article-cta-heading" className={styles.ctaTitle}>
            Нужен подбор привода?
          </h2>
          <p className={styles.ctaText}>
            Инженер поможет подобрать модель по ТТХ, крутящему моменту и сигналу
            управления.
          </p>
          <Link to="/consultation" className={styles.ctaLink}>
            Консультация инженера →
          </Link>
        </aside>

        <footer className={styles.footer}>
          <Link to="/statyi" className={styles.backLink}>
            ← Все статьи
          </Link>
        </footer>
      </article>

      {related.length > 0 ? (
        <section className={styles.related} aria-labelledby="related-heading">
          <h2 id="related-heading" className={styles.relatedTitle}>
            Читайте также
          </h2>
          <RelatedArticlesCarousel articles={related} />
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
