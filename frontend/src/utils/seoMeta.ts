/** SERP-oriented title/description helpers (docs/seo-meta-yandex-google.md). */

export const SITE_URL = "https://hoocon.ru";
const SITE_NAME = "Hoocon";
const TITLE_MAX = 60;
const TITLE_PARTIAL_MAX = TITLE_MAX - ` — ${SITE_NAME}`.length;
const DESC_MAX = 160;

const CATALOG_FALLBACK_DESCRIPTION =
  "Каталог электроприводов Hoocon для вентиляции и кондиционирования. "
  + "Фильтры по моменту, напряжению, типу; паспорта PDF; подбор аналогов Belimo.";

function truncateAtWord(text: string, maxLen: number): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= maxLen) {
    return clean;
  }
  const cut = clean.slice(0, maxLen - 1);
  const at = cut.lastIndexOf(" ");
  const base = at > 20 ? cut.slice(0, at) : cut;
  return `${base}…`;
}

/** Meta description capped at a word boundary (≤160). */
export function metaDescription(text: string, maxLen: number = DESC_MAX): string {
  return truncateAtWord(text, maxLen);
}

/**
 * Absolute URL for og:image (relative media → production origin).
 *
 * Args:
 *   src: Absolute or site-relative image URL.
 *
 * Returns:
 *   Absolute https URL, or undefined when src is empty.
 */
export function absoluteOgImageUrl(
  src: string | null | undefined,
): string | undefined {
  const raw = (src ?? "").trim();
  if (!raw) {
    return undefined;
  }
  if (raw.startsWith("https://") || raw.startsWith("http://")) {
    return raw;
  }
  if (raw.startsWith("//")) {
    return `https:${raw}`;
  }
  const path = raw.startsWith("/") ? raw : `/${raw}`;
  return `${SITE_URL}${path}`;
}

/**
 * Unique category listing description (align with backend ``_resolve_catalog_category``).
 *
 * Args:
 *   categoryName: Category display name.
 *   categoryDescription: Optional long description from API.
 */
export function categorySeoDescription(
  categoryName?: string | null,
  categoryDescription?: string | null,
): string {
  const fromBody = (categoryDescription ?? "").replace(/\s+/g, " ").trim();
  const fromName = (categoryName ?? "").replace(/\s+/g, " ").trim();
  const source = fromBody || fromName;
  if (!source) {
    return CATALOG_FALLBACK_DESCRIPTION;
  }
  return truncateAtWord(source, DESC_MAX);
}

export function brandedTitle(partial: string): string {
  if (partial.includes(SITE_NAME)) {
    return truncateAtWord(partial, TITLE_MAX);
  }
  const body = truncateAtWord(partial, TITLE_PARTIAL_MAX);
  return truncateAtWord(`${body} — ${SITE_NAME}`, TITLE_MAX);
}

export function skuSeoTitlePartial(
  skuCode: string,
  highlights?: Array<{ key: string; value: string }>,
): string {
  // Skip moment (Нм): already in article / on-page ТТХ — do not duplicate in <title>.
  const voltage = highlights?.find((h) => h.key === "voltage")?.value ?? "";
  const volt = shortVoltageForTitle(voltage);
  if (volt) {
    return `${skuCode} — ${volt}`;
  }
  return `${skuCode} — электропривод вентиляции`;
}

/** Collapse long voltage strings to ``24 В`` / ``230 В`` for SERP titles. */
function shortVoltageForTitle(voltage: string): string {
  const text = voltage.replace(/\s+/g, " ").trim();
  if (!text) return "";
  if (/(?:^|[^0-9])230(?:[^0-9]|$)/.test(text) || /100\s*\.\.\.\s*240/.test(text)) {
    return "230 В";
  }
  if (/(?:^|[^0-9])24(?:[^0-9]|$)/.test(text)) {
    return "24 В";
  }
  return text.length <= 12 ? text : text.slice(0, 12).trim();
}

export function skuSeoDescription(
  skuCode: string,
  categoryName?: string | null,
): string {
  if (categoryName?.trim()) {
    const cat = truncateAtWord(categoryName, 60);
    return truncateAtWord(
      `${skuCode}: ${cat}. Паспорт PDF, подбор аналогов Belimo, запрос КП у Hoocon.`,
      DESC_MAX,
    );
  }
  return truncateAtWord(
    `${skuCode}: электропривод вентиляции Hoocon. Паспорт PDF, фильтры по ` +
      "характеристикам, запрос коммерческого предложения.",
    DESC_MAX,
  );
}
