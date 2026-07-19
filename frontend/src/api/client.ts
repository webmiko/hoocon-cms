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
export type Category = components["schemas"]["Category"];
export type CategoryListResponse =
  paths["/api/catalog/categories/"]["get"]["responses"]["200"]["content"]["application/json"];

// SKU
export type SKUList = components["schemas"]["SKUList"];
export type SKUDetail = components["schemas"]["SKUDetail"];
export type SKUListResponse =
  paths["/api/catalog/skus/"]["get"]["responses"]["200"]["content"]["application/json"];
export type SKUDetailResponse =
  paths["/api/catalog/skus/{slug}/"]["get"]["responses"]["200"]["content"]["application/json"];

// Search
export type SearchResultItem = components["schemas"]["SearchResultItem"];
export type SearchResponse = components["schemas"]["SearchResponse"];

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

  skuDetail(slug: string): Promise<SKUDetailResponse> {
    return apiFetch<SKUDetailResponse>(`/api/catalog/skus/${slug}/`);
  },

  // ── Search ─────────────────────────────────────────────────────────
  search(q: string, page?: number): Promise<SearchResponse> {
    const params = new URLSearchParams({ q });
    if (page) params.set("page", String(page));
    return apiFetch<SearchResponse>(`/api/search/?${params.toString()}`);
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
