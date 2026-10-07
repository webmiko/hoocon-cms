import { Suspense } from "react";
import { Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";

import { CabinetGate } from "./account/CabinetGate";
import { ChunkLoadErrorBoundary } from "./components/ChunkLoadErrorBoundary";
import { Layout } from "./components/Layout";
import { PageFallback } from "./components/PageFallback";
import { HomePage } from "./pages/HomePage";
import { api } from "./api/client";
import { useAsync } from "./hooks/useAsync";
import { catalogPathForSku } from "./utils/catalogPaths";
import { shouldResolveLegacySkuSlug } from "./utils/legacySkuSlug";
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
const DocsPage = lazyWithChunkReload(() =>
  import("./pages/DocsPage").then((m) => ({ default: m.DocsPage })),
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
const LoginPage = lazyWithChunkReload(() => import("./account/LoginPage"));
const RegisterPage = lazyWithChunkReload(() => import("./account/RegisterPage"));
const AccountShell = lazyWithChunkReload(() => import("./account/AccountShell"));
const AccountDashboardPage = lazyWithChunkReload(() => import("./account/DashboardPage"));
const AccountLeadsPage = lazyWithChunkReload(() => import("./account/LeadsPage"));
const AccountQuotesPage = lazyWithChunkReload(() => import("./account/QuotesPage"));
const AccountOrdersPage = lazyWithChunkReload(() => import("./account/OrdersPage"));
const AccountDocumentsPage = lazyWithChunkReload(() => import("./account/DocumentsPage"));
const AccountSpecsPage = lazyWithChunkReload(() => import("./account/SpecsPage"));
const AccountConversationsPage = lazyWithChunkReload(() => import("./account/ConversationsPage"));
const AccountRmaPage = lazyWithChunkReload(() => import("./account/RmaPage"));
const AccountProfilePage = lazyWithChunkReload(() => import("./account/ProfilePage"));

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
  if (!slug || !shouldResolveLegacySkuSlug(slug)) {
    return (
      <Suspense fallback={<PageFallback />}>
        <NotFoundPage />
      </Suspense>
    );
  }
  return <SkuLegacyRedirectResolved slug={slug} />;
}

function SkuLegacyRedirectResolved({ slug }: { slug: string }) {
  const {
    data: sku,
    loading,
    error,
  } = useAsync((signal) => api.skuDetail(slug, { signal }), slug, `catalog:sku:${slug}`);

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
            <Route path="catalog/:categorySlug/:skuSlug" element={<SkuDetailPage />} />
            <Route path="compare" element={<ComparePage />} />
            <Route path="search" element={<SearchPage />} />
            <Route path="consultation" element={<LeadPage leadType="consultation" />} />
            <Route path="rfq" element={<LeadPage leadType="rfq" />} />
            <Route
              path="login"
              element={
                <CabinetGate>
                  <LoginPage />
                </CabinetGate>
              }
            />
            <Route
              path="register"
              element={
                <CabinetGate>
                  <RegisterPage />
                </CabinetGate>
              }
            />
            <Route
              path="account"
              element={
                <CabinetGate>
                  <AccountShell />
                </CabinetGate>
              }
            >
              <Route index element={<AccountDashboardPage />} />
              <Route path="leads" element={<AccountLeadsPage />} />
              <Route path="quotes" element={<AccountQuotesPage />} />
              <Route path="orders" element={<AccountOrdersPage />} />
              <Route path="documents" element={<AccountDocumentsPage />} />
              <Route path="specs" element={<AccountSpecsPage />} />
              <Route path="conversations" element={<AccountConversationsPage />} />
              <Route path="rma" element={<AccountRmaPage />} />
              <Route path="profile" element={<AccountProfilePage />} />
            </Route>
            <Route path="replacement" element={<LeadPage leadType="replacement" />} />
            <Route path="statyi" element={<ArticlesListPage />} />
            <Route path="statyi/:slug" element={<ArticlePage />} />
            <Route path="novosti" element={<NewsListPage />} />
            <Route path="novosti/:slug" element={<NewsPage />} />
            <Route path="news" element={<Navigate to="/novosti" replace />} />
            <Route path="news/*" element={<NewsLegacyRedirect />} />
            <Route path="company" element={<PageView slug="company" />} />
            <Route path="zavod" element={<PageView slug="zavod" />} />
            <Route path="gde-kupit" element={<WhereToBuyPage />} />
            <Route path="dokumentaciya" element={<DocsPage />} />
            <Route path="faq" element={<PageView slug="faq" />} />
            <Route path="kontakty" element={<PageView slug="kontakty" />} />
            <Route path="oferta" element={<PageView slug="oferta" />} />
            <Route path="privacy-policy" element={<PageView slug="privacy-policy" />} />
            <Route path="terms" element={<PageView slug="terms" />} />
            <Route path="o-kompanii" element={<Navigate to="/company" replace />} />
            <Route path="privacy" element={<Navigate to="/privacy-policy" replace />} />
            <Route path=":slug" element={<SkuLegacyRedirect />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </Suspense>
    </ChunkLoadErrorBoundary>
  );
}
