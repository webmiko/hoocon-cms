import { Suspense } from "react";
import { Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";

import { ChunkLoadErrorBoundary } from "./components/ChunkLoadErrorBoundary";
import { Layout } from "./components/Layout";
import { PageFallback } from "./components/PageFallback";
import { HomePage } from "./pages/HomePage";
import { api } from "./api/client";
import { useAsync } from "./hooks/useAsync";
import { catalogPathForSku } from "./utils/catalogPaths";
import { lazyWithChunkReload } from "./utils/lazyWithChunkReload";

const CatalogPage = lazyWithChunkReload(() =>
  import("./pages/CatalogPage").then((m) => ({ default: m.CatalogPage })),
);
const ComparePage = lazyWithChunkReload(() =>
  import("./pages/ComparePage").then((m) => ({ default: m.ComparePage })),
);
const SkuDetailPage = lazyWithChunkReload(() =>
  import("./pages/SkuDetailPage").then((m) => ({ default: m.SkuDetailPage })),
);
const ArticlesListPage = lazyWithChunkReload(() =>
  import("./pages/ArticlesListPage").then((m) => ({
    default: m.ArticlesListPage,
  })),
);
const ArticlePage = lazyWithChunkReload(() =>
  import("./pages/ArticlePage").then((m) => ({ default: m.ArticlePage })),
);
const NewsListPage = lazyWithChunkReload(() =>
  import("./pages/NewsListPage").then((m) => ({ default: m.NewsListPage })),
);
const NewsPage = lazyWithChunkReload(() =>
  import("./pages/NewsPage").then((m) => ({ default: m.NewsPage })),
);
const PageView = lazyWithChunkReload(() =>
  import("./pages/PageView").then((m) => ({ default: m.PageView })),
);
const WhereToBuyPage = lazyWithChunkReload(() =>
  import("./pages/WhereToBuyPage").then((m) => ({
    default: m.WhereToBuyPage,
  })),
);
const SearchPage = lazyWithChunkReload(() =>
  import("./pages/SearchPage").then((m) => ({ default: m.SearchPage })),
);
const LeadPage = lazyWithChunkReload(() =>
  import("./pages/LeadPage").then((m) => ({ default: m.LeadPage })),
);
const NotFoundPage = lazyWithChunkReload(() =>
  import("./pages/NotFoundPage").then((m) => ({ default: m.NotFoundPage })),
);

/**
 * Legacy Tilda /news/<a>/<b> → /novosti/<a>-<b>.
 */
function NewsLegacyRedirect() {
  const { pathname } = useLocation();
  const rest = pathname
    .replace(/^\/news\/?/, "")
    .split("/")
    .filter(Boolean)
    .join("-");
  return <Navigate to={rest ? `/novosti/${rest}` : "/novosti"} replace />;
}

/**
 * Legacy flat ``/:skuSlug`` → nested ``/catalog/{category}/{skuSlug}``.
 */
function SkuLegacyRedirect() {
  const { slug } = useParams<{ slug: string }>();
  const { data: sku, loading, error } = useAsync(
    () => api.skuDetail(slug!),
    slug,
    slug ? `catalog:sku:${slug}` : undefined,
  );

  if (!slug) {
    return (
      <Suspense fallback={<PageFallback />}>
        <NotFoundPage />
      </Suspense>
    );
  }
  if (loading) {
    return <PageFallback />;
  }
  if (error || !sku) {
    return (
      <Suspense fallback={<PageFallback />}>
        <NotFoundPage />
      </Suspense>
    );
  }
  const target = catalogPathForSku(sku);
  if (target === "/catalog") {
    return (
      <Suspense fallback={<PageFallback />}>
        <NotFoundPage />
      </Suspense>
    );
  }
  return <Navigate to={target} replace />;
}

/**
 * App routes for Hoocon CMS SPA.
 *
 * Home stays eager (LCP). Other pages are lazy so unused JS/CSS stay off the
 * critical path. Spec: ПЛАН Iter 4; Lighthouse unused JS/CSS.
 */
export default function App() {
  return (
    <ChunkLoadErrorBoundary>
      <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<HomePage />} />
            <Route path="catalog" element={<CatalogPage />} />
            <Route path="catalog/:categorySlug" element={<CatalogPage />} />
            <Route
              path="catalog/:categorySlug/:skuSlug"
              element={<SkuDetailPage />}
            />
            <Route path="compare" element={<ComparePage />} />
            <Route path="search" element={<SearchPage />} />
            <Route
              path="consultation"
              element={<LeadPage leadType="consultation" />}
            />
            <Route path="rfq" element={<LeadPage leadType="rfq" />} />
            <Route
              path="replacement"
              element={<LeadPage leadType="replacement" />}
            />
            <Route path="statyi" element={<ArticlesListPage />} />
            <Route path="statyi/:slug" element={<ArticlePage />} />
            <Route path="novosti" element={<NewsListPage />} />
            <Route path="novosti/:slug" element={<NewsPage />} />
            <Route path="news" element={<Navigate to="/novosti" replace />} />
            <Route path="news/*" element={<NewsLegacyRedirect />} />
            <Route path="company" element={<PageView slug="company" />} />
            <Route path="zavod" element={<PageView slug="zavod" />} />
            <Route path="gde-kupit" element={<WhereToBuyPage />} />
            <Route path="faq" element={<PageView slug="faq" />} />
            <Route path="kontakty" element={<PageView slug="kontakty" />} />
            <Route path="oferta" element={<PageView slug="oferta" />} />
            <Route
              path="privacy-policy"
              element={<PageView slug="privacy-policy" />}
            />
            <Route path="terms" element={<PageView slug="terms" />} />
            <Route
              path="o-kompanii"
              element={<Navigate to="/company" replace />}
            />
            <Route
              path="privacy"
              element={<Navigate to="/privacy-policy" replace />}
            />
            <Route path=":slug" element={<SkuLegacyRedirect />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </Suspense>
    </ChunkLoadErrorBoundary>
  );
}
