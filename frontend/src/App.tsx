import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { Layout } from "./components/Layout";
import { HomePage } from "./pages/HomePage";
import { CatalogPage } from "./pages/CatalogPage";
import { SkuDetailPage } from "./pages/SkuDetailPage";
import { ArticlesListPage } from "./pages/ArticlesListPage";
import { ArticlePage } from "./pages/ArticlePage";
import { NewsListPage } from "./pages/NewsListPage";
import { NewsPage } from "./pages/NewsPage";
import { PageView } from "./pages/PageView";
import { WhereToBuyPage } from "./pages/WhereToBuyPage";
import { SearchPage } from "./pages/SearchPage";
import { LeadPage } from "./pages/LeadPage";
import { NotFoundPage } from "./pages/NotFoundPage";

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
 * App routes for Hoocon CMS SPA.
 *
 * Canonical CMS pages match docs/seo-url-migration.md:
 * /company, /gde-kupit, /oferta, /privacy-policy, /terms, /faq, /kontakty.
 */
export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="catalog" element={<CatalogPage />} />
        <Route path="search" element={<SearchPage />} />
        <Route
          path="consultation"
          element={<LeadPage leadType="consultation" />}
        />
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
        <Route path="gde-kupit" element={<WhereToBuyPage />} />
        <Route path="faq" element={<PageView slug="faq" />} />
        <Route path="kontakty" element={<PageView slug="kontakty" />} />
        <Route path="oferta" element={<PageView slug="oferta" />} />
        <Route
          path="privacy-policy"
          element={<PageView slug="privacy-policy" />}
        />
        <Route path="terms" element={<PageView slug="terms" />} />
        {/* Legacy aliases → canonical SEO paths */}
        <Route path="o-kompanii" element={<Navigate to="/company" replace />} />
        <Route
          path="privacy"
          element={<Navigate to="/privacy-policy" replace />}
        />
        <Route path=":slug" element={<SkuDetailPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
