/**
 * API client for Hoocon CMS backend (DRF + drf-spectacular).
 *
 * Types are generated from the OpenAPI schema (see `schema.d.ts`).
 * Run `npm run gen:api` to regenerate after backend changes.
 *
 * Spec: ПЛАН §6; docs/readiness-backend-ux.md §2.3.
 */

import type { components, paths } from "./schema";

// ── Re-export generated types for convenience ────────────────────────

export type { paths, components };

// Category
export type Category = components["schemas"]["Category"] & {
  image?: { id: number; image: string; alt?: string } | null;
};
export type CategoryListResponse =
  paths["/api/catalog/categories/"]["get"]["responses"]["200"]["content"]["application/json"];

// SKU
export type SKUList = components["schemas"]["SKUList"] & {
  highlights?: CatalogHighlight[];
  image?: { id: number; image: string; alt?: string } | null;
  in_stock?: boolean;
  /** Published SKU count on the same Product (family cards). */
  edition_count?: number;
};
export type CatalogAttribute = {
  name: string;
  slug: string;
  unit: string;
  value: string;
  group?: string;
  group_label?: string;
};

export type CatalogAttributeGroup = {
  key: string;
  title: string;
  items: CatalogAttribute[];
};

export type SKUDetail = components["schemas"]["SKUDetail"] & {
  highlights?: CatalogHighlight[];
  attributes?: CatalogAttribute[];
  attribute_groups?: CatalogAttributeGroup[];
  images?: Array<{ id: number; image: string; alt?: string }>;
  lead?: string;
  specs_text?: string;
  analogs_text?: string;
  category_name?: string;
  category_description?: string;
  category_instructions?: string;
  ball_valve_kit?: {
    drive_families: string[];
    suffixes: string[];
    bracket_by_drive: Record<string, string>;
    bracket_hint: string;
  } | null;
  siblings?: Array<{
    slug: string;
    sku_code: string;
    body: string;
    dn: string;
    ways: string;
    kvs: string;
    voltage: string;
    control: string;
    aux_switch: boolean;
    fault_alarm?: boolean;
    in_stock: boolean;
  }>;
  variant_axes?: Record<string, string[]>;
};
export type SKUListResponse =
  paths["/api/catalog/skus/"]["get"]["responses"]["200"]["content"]["application/json"];
/** Detail payload with app-side fields not yet in OpenAPI schema.d.ts. */
export type SKUDetailResponse = SKUDetail;

export interface CatalogHighlight {
  key: string;
  name: string;
  value: string;
  unit: string;
}

export interface CatalogFacetValue {
  value: string;
  count: number;
}

export interface CatalogFacet {
  key: string;
  label: string;
  values: CatalogFacetValue[];
}

export interface CatalogFacetsResponse {
  results: CatalogFacet[];
}

export interface CompareRow {
  key: string;
  name: string;
  values: string[];
  diff: boolean;
  group?: string;
  group_title?: string;
  /** True for highlights/meta; false for full attribute-group rows. */
  core?: boolean;
}

export interface CompareResponse {
  skus: SKUList[];
  rows: CompareRow[];
}

// Search
export type SearchResultItem = components["schemas"]["SearchResultItem"];
export type SearchResponse = components["schemas"]["SearchResponse"];

// Content (Page / Article / News)
export type Page = components["schemas"]["Page"];
export type Article = components["schemas"]["Article"] & {
  excerpt?: string;
  cover?: string | null;
  related_skus?: Array<{
    name: string;
    slug: string;
    sku_code: string;
    category_slug?: string;
    image: string | null;
  }>;
};
export type News = components["schemas"]["News"] & {
  cover?: string | null;
};

// Lead (request payload)
export type LeadCreate = components["schemas"]["Lead"];

// ── API base URL ──────────────────────────────────────────────────────

// In dev, Vite proxies /api to Django (see vite.config.ts).
// In prod, nginx serves the SPA and proxies /api to gunicorn.
const API_BASE = "";

// ── Fetch helper ─────────────────────────────────────────────────────

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, error);
  }

  // 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

// ── API error ─────────────────────────────────────────────────────────

export class ApiError extends Error {
  status: number;
  body: { detail?: string; [key: string]: unknown };

  constructor(status: number, body: { detail?: string; [key: string]: unknown }) {
    super(`API ${status}: ${body.detail ?? "Unknown error"}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

// ── CSRF token (for POST /api/leads/) ────────────────────────────────

function getCsrfToken(): string | null {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : null;
}

// ── API endpoints ────────────────────────────────────────────────────

export const api = {
  // ── Catalog ───────────────────────────────────────────────────────
  categories(): Promise<CategoryListResponse> {
    return apiFetch<CategoryListResponse>("/api/catalog/categories/");
  },

  skus(params?: Record<string, string>): Promise<SKUListResponse> {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return apiFetch<SKUListResponse>(`/api/catalog/skus/${qs}`);
  },

  facets(params?: { category?: string }): Promise<CatalogFacetsResponse> {
    const qs = params?.category
      ? `?${new URLSearchParams({ category: params.category }).toString()}`
      : "";
    return apiFetch<CatalogFacetsResponse>(`/api/catalog/facets/${qs}`);
  },

  skuDetail(slug: string): Promise<SKUDetailResponse> {
    return apiFetch<SKUDetailResponse>(`/api/catalog/skus/${slug}/`);
  },

  compare(slugs: string[]): Promise<CompareResponse> {
    const qs =
      slugs.length > 0
        ? `?${new URLSearchParams({ skus: slugs.join(",") }).toString()}`
        : "";
    return apiFetch<CompareResponse>(`/api/catalog/compare/${qs}`);
  },

  // ── Content ───────────────────────────────────────────────────────
  pages(): Promise<{ count: number; results: Page[] }> {
    return apiFetch("/api/content/pages/");
  },

  pageDetail(slug: string): Promise<Page> {
    return apiFetch(`/api/content/pages/${slug}/`);
  },

  articles(): Promise<{ count: number; results: Article[] }> {
    return apiFetch("/api/content/articles/");
  },

  articleDetail(slug: string): Promise<Article> {
    return apiFetch(`/api/content/articles/${slug}/`);
  },

  news(): Promise<{ count: number; results: News[] }> {
    return apiFetch("/api/content/news/");
  },

  newsDetail(slug: string): Promise<News> {
    return apiFetch(`/api/content/news/${slug}/`);
  },

  // ── Search ─────────────────────────────────────────────────────────
  search(q: string, page?: number): Promise<SearchResponse> {
    const params = new URLSearchParams({ q });
    if (page) params.set("page", String(page));
    return apiFetch<SearchResponse>(`/api/search/?${params.toString()}`);
  },

  // ── CSRF ──────────────────────────────────────────────────────────
  /**
   * Fetch the CSRF cookie before POST /api/leads/.
   *
   * Prefer calling from LeadForm mount (not app bootstrap) so home/catalog
   * keep /api/csrf/ off the Lighthouse critical path.
   */
  fetchCsrfToken(): Promise<{ csrfToken: string }> {
    return apiFetch<{ csrfToken: string }>("/api/csrf/");
  },

  // ── Leads ──────────────────────────────────────────────────────────
  createLead(data: Record<string, unknown>): Promise<{ id: number | null; status: string }> {
    return apiFetch("/api/leads/", {
      method: "POST",
      body: JSON.stringify(data),
      headers: {
        "X-CSRFToken": getCsrfToken() ?? "",
      },
    });
  },
};
