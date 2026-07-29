import { Link, useParams } from "react-router-dom";

import { Breadcrumbs } from "../components/Breadcrumbs";
import { Seo } from "../components/Seo";
import { api } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { sanitizeHtml } from "../utils/sanitize";
import { buildBreadcrumbJsonLd, buildFaqJsonLd } from "../utils/jsonLd";
import { metaDescription } from "../utils/seoMeta";
import styles from "./PageView.module.css";
import "../styles/cms-body-charts.css";

interface PageViewProps {
  /** Explicit slug when route has no :slug param (e.g. /o-kompanii). */
  slug?: string;
}

/**
 * Static CMS page (/o-kompanii, /kontakty, /privacy, …).
 * Spec: ПЛАН §6 Iter 4; docs/readiness-backend-ux.md §2.2.
 */
export function PageView({ slug: slugProp }: PageViewProps) {
  const params = useParams<{ slug: string }>();
  const slug = slugProp ?? params.slug ?? "";
  const { data: page, loading, error } = useAsync(
    () => api.pageDetail(slug),
    slug,
  );

  if (!slug) {
    return (
      <div className={styles.notFound}>
        <h1>Страница не найдена</h1>
        <Link to="/" className={styles.link}>
          ← На главную
        </Link>
      </div>
    );
  }

  if (loading) {
    return <p className={styles.status}>Загрузка…</p>;
  }

  if (error || !page) {
    return (
      <div className={styles.notFound}>
        <h1>Страница не найдена</h1>
        <Link to="/" className={styles.link}>
          ← На главную
        </Link>
      </div>
    );
  }

  const desc = metaDescription(page.body.replace(/<[^>]+>/g, ""));
  const jsonLd =
    page.slug === "faq"
      ? [buildFaqJsonLd(), buildBreadcrumbJsonLd([
          { name: "Главная", path: "/" },
          { name: page.title, path: `/${page.slug}` },
        ])]
      : [
          buildBreadcrumbJsonLd([
            { name: "Главная", path: "/" },
            { name: page.title, path: `/${page.slug}` },
          ]),
        ];

  const isLanding = page.slug === "zavod";
  const seoDescription =
    page.slug === "zavod"
      ? "OEM электроприводов вентиляции и кондиционирования под вашим брендом напрямую с завода Ningbo Hoocon: CE, UL, EAC. Без посредников."
      : desc;

  const crumbs = (
    <Breadcrumbs
      items={[
        { label: "Главная", to: "/" },
        { label: page.title },
      ]}
    />
  );
  const heading = <h1 className={styles.title}>{page.title}</h1>;
  const body = (
    <div
      className={`${styles.body} cms-rich-body${isLanding ? ` ${styles.bodyLanding}` : ""}`}
      dangerouslySetInnerHTML={{ __html: sanitizeHtml(page.body) }}
    />
  );

  return (
    <article className={isLanding ? styles.pageLanding : styles.page}>
      <Seo
        title={page.title}
        description={seoDescription}
        path={`/${page.slug}`}
        jsonLd={jsonLd}
      />
      {isLanding ? (
        <div className={styles.landingInner}>
          {crumbs}
          {heading}
          {body}
        </div>
      ) : (
        <>
          {crumbs}
          {heading}
          {body}
        </>
      )}
    </article>
  );
}
