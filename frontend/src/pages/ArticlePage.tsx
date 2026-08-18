import { Link, useParams } from "react-router-dom";

import { RelatedArticlesCarousel } from "../components/RelatedArticlesCarousel";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { ProtectedProductImage } from "../components/ProtectedProductImage";
import { Seo } from "../components/Seo";
import { ThemeAwareCover } from "../components/ThemeAwareCover";
import { api } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { sanitizeHtml } from "../utils/sanitize";
import { extractArticleToc } from "../utils/articleToc";
import { generatedCoverCaption } from "../utils/generatedCoverCaption";
import { stripHtmlToText } from "../utils/stripHtml";
import {
  buildArticleJsonLd,
  buildBreadcrumbJsonLd,
} from "../utils/jsonLd";
import { catalogPathForSku } from "../utils/catalogPaths";
import { protectedContentHandlers } from "../utils/contentProtection";
import { metaDescription } from "../utils/seoMeta";
import styles from "./ArticlePage.module.css";
import "../styles/cms-body-charts.css";

const TOC_MIN_SECTIONS = 3;

/**
 * Article detail — readable column, scannable hierarchy, related links.
 * Spec: readiness §4.3 OEM support; WCAG reading comfort (65–75ch, 1.7 lh).
 */
export function ArticlePage() {
  const { slug } = useParams<{ slug: string }>();
  const { data: article, loading, error } = useAsync(
    () => api.articleDetail(slug!),
    slug,
  );
  const { data: listData } = useAsync(() => api.articles());

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

  const bodyWithToc = extractArticleToc(sanitizeHtml(article.body));
  const plain = stripHtmlToText(article.excerpt || article.body);
  const description = metaDescription(plain);
  const minutes = readingMinutes(article.body);
  const related = (listData?.results ?? [])
    .filter((item) => item.slug !== article.slug)
    .slice(0, 8);
  const showToc = bodyWithToc.items.length >= TOC_MIN_SECTIONS;
  const coverCaption = generatedCoverCaption("article", article.slug);
  const coverClassName = coverCaption ? `${styles.cover} ${styles.coverGenerated}` : styles.cover;

  return (
    <div className={styles.page}>
      <article className={styles.article}>
        <Seo
          title={article.title}
          description={description}
          path={`/statyi/${article.slug}`}
          ogType="article"
          image={article.cover}
          jsonLd={[
            buildArticleJsonLd({
              title: article.title,
              slug: article.slug,
              description,
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
            <ThemeAwareCover
              light={article.cover}
              dark={article.cover_dark}
              alt={article.title}
              imgClassName={coverClassName}
              loading="eager"
            />
            {coverCaption ? (
              <figcaption className={styles.coverCaption}>{coverCaption}</figcaption>
            ) : null}
          </figure>
        ) : null}

        <div className={styles.layout}>
          {showToc ? (
            <>
              <nav
                className={styles.tocDesktop}
                aria-label="Содержание статьи"
              >
                <p className={styles.tocHeading}>Содержание</p>
                <ol className={styles.tocList}>
                  {bodyWithToc.items.map((item) => (
                    <li
                      key={item.id}
                      className={
                        item.level === 3 ? styles.tocItemH3 : styles.tocItemH2
                      }
                    >
                      <a href={`#${item.id}`} className={styles.tocLink}>
                        {item.text}
                      </a>
                    </li>
                  ))}
                </ol>
              </nav>
              <details className={styles.tocMobile}>
                <summary className={styles.tocSummary}>Содержание</summary>
                <ol className={styles.tocList}>
                  {bodyWithToc.items.map((item) => (
                    <li
                      key={`m-${item.id}`}
                      className={
                        item.level === 3 ? styles.tocItemH3 : styles.tocItemH2
                      }
                    >
                      <a href={`#${item.id}`} className={styles.tocLink}>
                        {item.text}
                      </a>
                    </li>
                  ))}
                </ol>
              </details>
            </>
          ) : null}

          {/* Body HTML from CMS; DOMPurify — security-baseline §3.6 (id kept for TOC) */}
          <div
            className={`${styles.body} cms-rich-body`}
            dangerouslySetInnerHTML={{ __html: sanitizeHtml(bodyWithToc.html) }}
          />
        </div>

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
                        frameClassName={styles.productImage}
                        className="u-protect-media"
                        compact
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
            Инженер поможет подобрать модель по характеристикам, крутящему моменту и сигналу
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
