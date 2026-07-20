/** SERP-oriented title/description helpers (docs/seo-meta-yandex-google.md). */

const SITE_NAME = "Hoocon";
const TITLE_MAX = 60;
const TITLE_PARTIAL_MAX = TITLE_MAX - ` — ${SITE_NAME}`.length;
const DESC_MAX = 160;

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
  return `${skuCode} — электропривод ОВК`;
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
    `${skuCode}: электропривод ОВК Hoocon. Паспорт PDF, фильтры по ТТХ, ` +
      "запрос коммерческого предложения.",
    DESC_MAX,
  );
}
