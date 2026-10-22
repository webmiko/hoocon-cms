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
  if (source.length < 80) {
    return truncateAtWord(
      `${source}. Подбор Hoocon по моменту и напряжению, паспорта PDF, запрос КП.`,
      DESC_MAX,
    );
  }
  return truncateAtWord(source, DESC_MAX);
}

const CATALOG_ROOT_TITLE = "Каталог электроприводов для вентиляции";
const SHORT_TITLE_MIN = 24;
const SHORT_TITLE_TAIL = " для электроприводов";

function lengthenShortTitle(name: string): string {
  if (name.length >= SHORT_TITLE_MIN) {
    return name;
  }
  return `${name}${SHORT_TITLE_TAIL}`;
}

/** Listing page <title>: unique per category; never reuse the root /catalog title. */
export function catalogListingSeoTitle(
  categorySlug?: string,
  categoryName?: string | null,
): string {
  const name = (categoryName ?? "").trim();
  if (name) {
    return lengthenShortTitle(name);
  }
  const slug = (categorySlug ?? "").trim();
  if (slug) {
    return `Каталог — ${slug}`;
  }
  return CATALOG_ROOT_TITLE;
}

/** PDP 404: include slug so broken legacy URLs do not share one SERP title. */
export function skuNotFoundSeoTitle(slug: string): string {
  const code = (slug ?? "").trim();
  if (!code) {
    return "Товар не найден";
  }
  return truncateAtWord(`Товар не найден — ${code}`, TITLE_PARTIAL_MAX);
}

export function brandedTitle(partial: string): string {
  if (partial.includes(SITE_NAME)) {
    return truncateAtWord(partial, TITLE_MAX);
  }
  const body = truncateAtWord(partial, TITLE_PARTIAL_MAX);
  return truncateAtWord(`${body} — ${SITE_NAME}`, TITLE_MAX);
}

function skuKindForTitle(categoryName?: string | null): string {
  const name = (categoryName ?? "").toLocaleLowerCase("ru");
  if (name.includes("кран")) return "кран";
  if (name.includes("адаптер")) return "адаптер";
  if (name.includes("комплект")) return "комплект";
  if (name.includes("кронштейн")) return "кронштейн";
  return "привод";
}

/** Same shape as backend ``sku_meta_title_partial``: code, kind, torque, voltage, analog. */
export function skuSeoTitlePartial(
  skuCode: string,
  highlights?: Array<{ key: string; value: string }>,
  analog?: string | null,
  categoryName?: string | null,
): string {
  const voltage = highlights?.find((h) => h.key === "voltage")?.value ?? "";
  const momentRaw = highlights?.find((h) => h.key === "moment")?.value ?? "";
  const moment = momentRaw.replace(/\s+/g, " ").trim();
  const volt = shortVoltageForTitle(voltage);
  const analogBit = (analog ?? "").replace(/\s+/g, " ").trim();
  const kind = skuKindForTitle(categoryName);
  const parts = [skuCode, kind];
  if (moment && moment.length <= 12) parts.push(moment);
  if (volt) parts.push(volt);
  let partial = parts.join(" ");
  if (analogBit) {
    const withAnalog = `${partial}, аналог ${analogBit}`;
    if (withAnalog.length <= TITLE_PARTIAL_MAX) partial = withAnalog;
  }
  if (partial.length <= TITLE_PARTIAL_MAX) return partial;
  const shorter = [skuCode];
  if (moment && moment.length <= 12) shorter.push(moment);
  if (volt) shorter.push(volt);
  partial = shorter.join(" ");
  return partial.length <= TITLE_PARTIAL_MAX
    ? partial
    : partial.slice(0, TITLE_PARTIAL_MAX);
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
  highlights?: Array<{ key: string; value: string }>,
  analog?: string | null,
): string {
  const bits = [`${skuCode}:`];
  if (categoryName?.trim()) {
    bits.push(`${truncateAtWord(categoryName, 60)}.`);
  } else {
    bits.push("электропривод вентиляции Hoocon.");
  }
  const moment = highlights?.find((h) => h.key === "moment")?.value?.replace(/\s+/g, " ").trim() ?? "";
  const volt = shortVoltageForTitle(
    highlights?.find((h) => h.key === "voltage")?.value ?? "",
  );
  const facts = [moment, volt].filter(Boolean);
  if (facts.length) bits.push(`${facts.join(" ")}.`);
  const analogBit = (analog ?? "").replace(/\s+/g, " ").trim();
  if (analogBit) bits.push(`Аналог Belimo ${analogBit}.`);
  bits.push("Паспорт PDF, запрос КП у Hoocon.");
  return truncateAtWord(bits.join(" "), DESC_MAX);
}
