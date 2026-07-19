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
  const moment = highlights?.find((h) => h.key === "moment")?.value ?? "";
  const voltage = highlights?.find((h) => h.key === "voltage")?.value ?? "";
  const specs = [moment, voltage].filter(Boolean).join(", ");
  if (specs) {
    return `${skuCode} — ${specs}`;
  }
  return `${skuCode} — электропривод ОВК`;
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
