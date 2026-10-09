/**
 * DRF error bodies → one readable Russian line (no imports: used by API clients).
 *
 * Shapes: ``{detail}``, ``{non_field_errors: [...]}``, ``{field: ["..."]}``,
 * nested ``{items: [{}, {quantity: ["..."]}]}`` or a bare list/string.
 */

const FORM_LEVEL_KEYS = ["detail", "non_field_errors"] as const;

function firstMessage(value: unknown): string {
  if (typeof value === "string") return value.trim();
  if (Array.isArray(value)) {
    for (const item of value) {
      const msg = firstMessage(item);
      if (msg) return msg;
    }
    return "";
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of FORM_LEVEL_KEYS) {
      const msg = firstMessage(record[key]);
      if (msg) return msg;
    }
    for (const [key, item] of Object.entries(record)) {
      if ((FORM_LEVEL_KEYS as readonly string[]).includes(key)) continue;
      const msg = firstMessage(item);
      if (msg) return msg;
    }
  }
  return "";
}

/** First human message in a DRF error body, or "" when there is none. */
export function drfErrorMessage(body: unknown): string {
  return firstMessage(body);
}

/** Top-level field → first message (nested list items collapse into their field). */
export function drfFieldErrors(body: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (!body || typeof body !== "object" || Array.isArray(body)) return out;
  for (const [key, value] of Object.entries(body as Record<string, unknown>)) {
    const msg = firstMessage(value);
    if (msg) out[key] = msg;
  }
  return out;
}

/** Fallback when the body says nothing (HTTP/2 has no statusText). */
export function httpStatusMessage(status: number): string {
  if (status === 400) return "Проверьте введённые данные.";
  if (status === 401 || status === 403) return "Нужно войти заново.";
  if (status === 404) return "Не найдено.";
  if (status === 413) return "Файл слишком большой.";
  if (status === 429) return "Слишком много попыток. Подождите минуту.";
  if (status >= 500) return "Сервер временно недоступен. Попробуйте позже.";
  return "Не удалось выполнить запрос.";
}

/** Readable message for a failed response body + status. */
export function responseErrorMessage(status: number, body: unknown): string {
  return drfErrorMessage(body) || httpStatusMessage(status);
}

const API_ERROR_NAMES = new Set(["ApiError", "AccountApiError"]);

/**
 * Message for a caught error in UI: API errors carry a readable message
 * already; fetch network failures («Failed to fetch») and anything else
 * get Russian text instead of a raw English/"[object Object]" string.
 */
export function userErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && API_ERROR_NAMES.has(err.name) && err.message) {
    return err.message;
  }
  if (err instanceof TypeError) {
    return "Нет связи с сервером. Проверьте интернет и попробуйте ещё раз.";
  }
  return fallback;
}
