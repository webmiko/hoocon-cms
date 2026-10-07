/**
 * Client cabinet API — ``/api/auth/*`` + ``/api/account/*``.
 *
 * Session cookie auth (no JWT in localStorage): POSTs carry the CSRF
 * header exactly like ``api.createLead``. Types are hand-rolled — the
 * cabinet contract is internal and intentionally not in the public
 * OpenAPI schema surface used by the catalog client.
 */

export type ClientSession = {
  email: string;
  name: string;
  phone: string;
  auth_modes: string[];
  features: Record<string, boolean>;
};

export type LeadItem = {
  id: number;
  sku_code: string;
  sku: number | null;
  name: string;
  quantity: number;
};

export type AccountLead = {
  id: number;
  type: string;
  type_label: string;
  status: string;
  status_label: string;
  company: string;
  message: string;
  created_at: string;
  items: LeadItem[];
  quotes?: AccountQuote[];
};

export type AccountQuote = {
  id: number;
  number: string;
  status: string;
  status_label: string;
  comment: string;
  total_amount: string | null;
  sent_at: string | null;
  created_at: string;
};

export type AccountDocument = {
  id: number;
  title: string;
  kind: string;
  kind_label: string;
  edo_status: string;
  edo_status_label: string;
  quote: number | null;
  order: number | null;
  created_at: string;
};

export type AccountOrder = {
  id: number;
  number: string;
  status: string;
  status_label: string;
  progress: number;
  planned_ship_date: string | null;
  carrier: string;
  carrier_label: string;
  track_number: string;
  items: LeadItem[];
  created_at: string;
};

export type SpecList = {
  id: number;
  name: string;
  note: string;
  items: Array<{
    id: number;
    sku_code: string;
    sku: number | null;
    quantity: number;
    position: number;
  }>;
  created_at: string;
  updated_at: string;
};

export type AccountConversation = {
  id: number;
  subject: string;
  status: string;
  status_label: string;
  channel: string;
  channel_label: string;
  updated_at: string;
};

export type RmaCase = {
  id: number;
  subject: string;
  description: string;
  serial_number: string;
  order: number | null;
  status: string;
  status_label: string;
  has_photo: boolean;
  created_at: string;
};

export type AccountSummary = {
  active_leads: number;
  quotes_pending: number;
  orders_in_work: number;
  unread_conversations: number;
};

export type AccountCompany = {
  name: string;
  inn: string;
  legal_address: string;
  members: Array<{ id: number; role: string; role_label: string; client: number | null }>;
};

export class AccountApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail || `API ${status}`);
    this.name = "AccountApiError";
    this.status = status;
    this.detail = detail;
  }
}

function csrfToken(): string {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : "";
}

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.method && init.method !== "GET" ? { "X-CSRFToken": csrfToken() } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new AccountApiError(response.status, body.detail ?? response.statusText);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export const accountApi = {
  // ── Auth (/api/auth/*) ────────────────────────────────────────────
  /** GET /api/csrf/ — puts the csrftoken cookie in place before POSTs. */
  csrf(): Promise<{ csrfToken: string }> {
    return call<{ csrfToken: string }>("/api/csrf/");
  },
  me(): Promise<ClientSession> {
    return call<ClientSession>("/api/auth/me/");
  },
  register(data: {
    email: string;
    password: string;
    name?: string;
    phone?: string;
    form_start_ts?: number;
    website?: string;
  }): Promise<ClientSession> {
    return call<ClientSession>("/api/auth/register/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },
  login(email: string, password: string): Promise<ClientSession> {
    return call<ClientSession>("/api/auth/login/", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },
  otpStart(
    email: string,
    formStartTs: number,
  ): Promise<{ challenge_id: string; email_masked: string }> {
    return call("/api/auth/otp/start/", {
      method: "POST",
      body: JSON.stringify({ email, form_start_ts: formStartTs }),
    });
  },
  otpVerify(challengeId: string, code: string): Promise<ClientSession> {
    return call<ClientSession>("/api/auth/otp/verify/", {
      method: "POST",
      body: JSON.stringify({ challenge_id: challengeId, code }),
    });
  },
  otpResend(challengeId: string): Promise<{ challenge_id: string; email_masked: string }> {
    return call("/api/auth/otp/resend/", {
      method: "POST",
      body: JSON.stringify({ challenge_id: challengeId }),
    });
  },
  logout(): Promise<void> {
    return call<void>("/api/auth/logout/", { method: "POST" });
  },

  // ── Cabinet (/api/account/*) ──────────────────────────────────────
  summary(): Promise<AccountSummary> {
    return call<AccountSummary>("/api/account/summary/");
  },
  updateProfile(data: { name?: string; phone?: string }): Promise<ClientSession> {
    return call<ClientSession>("/api/account/me/", {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },
  leads(status?: string): Promise<{ results: AccountLead[] } | AccountLead[]> {
    const qs = status ? `?status=${encodeURIComponent(status)}` : "";
    return call(`/api/account/leads/${qs}`);
  },
  lead(id: number): Promise<AccountLead> {
    return call(`/api/account/leads/${id}/`);
  },
  repeatLead(id: number): Promise<AccountLead> {
    return call(`/api/account/leads/${id}/repeat/`, { method: "POST" });
  },
  specs(): Promise<SpecList[]> {
    return call("/api/account/specs/");
  },
  saveSpec(data: {
    id?: number;
    name: string;
    note?: string;
    items?: Array<{ sku_code: string; sku?: number | null; quantity: number }>;
  }): Promise<SpecList> {
    if (data.id) {
      return call(`/api/account/specs/${data.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ name: data.name, note: data.note, items: data.items }),
      });
    }
    return call("/api/account/specs/", {
      method: "POST",
      body: JSON.stringify({ name: data.name, note: data.note, items: data.items }),
    });
  },
  deleteSpec(id: number): Promise<void> {
    return call(`/api/account/specs/${id}/`, { method: "DELETE" });
  },
  specToLead(id: number): Promise<AccountLead> {
    return call(`/api/account/specs/${id}/to_lead/`, { method: "POST" });
  },
  quotes(): Promise<AccountQuote[]> {
    return call("/api/account/quotes/");
  },
  documents(): Promise<AccountDocument[]> {
    return call("/api/account/documents/");
  },
  documentDownloadUrl(id: number): string {
    return `/api/account/documents/${id}/download/`;
  },
  documentsZipUrl(): string {
    return "/api/account/documents/zip/";
  },
  quotePdfUrl(id: number): string {
    return `/api/account/quotes/${id}/pdf/`;
  },
  orders(): Promise<AccountOrder[]> {
    return call("/api/account/orders/");
  },
  conversations(): Promise<AccountConversation[]> {
    return call("/api/account/conversations/");
  },
  company(): Promise<AccountCompany> {
    return call("/api/account/company/");
  },
  rmaCases(): Promise<RmaCase[]> {
    return call("/api/account/rma/");
  },
  createRma(data: {
    subject: string;
    description?: string;
    serial_number?: string;
    order?: number | null;
    photo?: File | null;
  }): Promise<RmaCase> {
    if (data.photo) {
      // Multipart — no JSON content-type; browser sets the boundary.
      const form = new FormData();
      form.set("subject", data.subject);
      if (data.description) form.set("description", data.description);
      if (data.serial_number) form.set("serial_number", data.serial_number);
      if (data.order) form.set("order", String(data.order));
      form.set("photo", data.photo);
      return callForm<RmaCase>("/api/account/rma/", form);
    }
    return call("/api/account/rma/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },
  rmaPhotoUrl(id: number): string {
    return `/api/account/rma/${id}/photo/`;
  },
};

async function callForm<T>(url: string, form: FormData): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": csrfToken() },
    body: form,
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new AccountApiError(response.status, body.detail ?? response.statusText);
  }
  return response.json() as Promise<T>;
}
