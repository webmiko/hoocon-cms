import { Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { HomePage } from "./pages/HomePage";
import { CatalogPage } from "./pages/CatalogPage";
import { SkuDetailPage } from "./pages/SkuDetailPage";
import { ArticlePage } from "./pages/ArticlePage";
import { NewsPage } from "./pages/NewsPage";
import { PageView } from "./pages/PageView";
import { SearchPage } from "./pages/SearchPage";
import { NotFoundPage } from "./pages/NotFoundPage";

/**
 * App routes for Hoocon CMS SPA.
 *
 * Path convention (canonical, matches Tilda sitemap — see
 * docs/seo-url-migration.md):
 * - /                        → home
 * - /catalog/                → catalog list (filters via query string)
 * - /<slug>/                 → SKU detail (canonical SKU path)
 * - /statyi/<slug>/          → article detail
 * - /novosti/<slug>/          → news detail
 * - /<page-slug>/            → static CMS page (e.g. /o-kompanii/)
 * - /search/                 → search results (?q=)
 *
 * Note: SKU slugs and Page slugs share the root namespace. The backend
 * resolves /<slug>/ by trying SKU first, then Page. On the frontend we
 * use a single catch-all route that fetches and renders accordingly.
 */
export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="catalog" element={<CatalogPage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="statyi/:slug" element={<ArticlePage />} />
        <Route path="novosti/:slug" element={<NewsPage />} />
        {/* Catch-all: SKU detail or CMS page (resolved by slug on backend) */}
        <Route path=":slug" element={<SkuDetailPage />} />
        <Route path=":slug/*" element={<PageView />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
