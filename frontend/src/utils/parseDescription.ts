/** Parse catalog description (lead + bullets + section titles) into semantic HTML. */

const BULLET_RE = /^[–—\-•·*]\s+/;
/** ``Основные особенности:`` or colon-less titles like ``Преимущества``. */
const SECTION_RE = /^(.{2,60}):\s*$/;
const SECTION_BARE_RE = new RegExp(
  "^(" +
    "основные особенности|области применения|" +
    "область применения|сфера применения|" +
    "преимущества|отличительные преимущества|" +
    "конкурентные преимущества(?:\\s+перед\\s+аналогами)?|" +
    "функциональные особенности|технические возможности|" +
    "ключевые характеристики|конструктивные особенности|" +
    "эксплуатационные параметры|безопасность и сертификация|" +
    "важные замечания(?:\\s+по\\s+эксплуатации)?|" +
    "технические характеристики|комплектация|назначение|" +
    "общие характеристики аналогов|преимущества серии\\s+.+" +
    ")$",
  "i",
);

export type DescriptionBlock =
  | { type: "paragraph"; text: string }
  | { type: "section"; title: string }
  | { type: "list"; items: string[] };

/**
 * Split a structured plain-text product description into renderable blocks.
 *
 * Expected input shape (from ETL):
 * - lead paragraph(s)
 * - optional ``Title:`` / bare section headers
 * - ``– item`` bullet lines
 *
 * Duplicate lines (same text ignoring case/bullets) are dropped.
 */
export function parseDescription(raw: string): DescriptionBlock[] {
  const text = raw.replace(/\u00a0/g, " ").trim();
  if (!text) return [];

  const blocks: DescriptionBlock[] = [];
  let paragraphBuf: string[] = [];
  let listBuf: string[] = [];
  const seen = new Set<string>();

  const lineKey = (line: string) =>
    line
      .toLowerCase()
      .replace(/^[–—\-•·*]+\s*/, "")
      .replace(/\s+/g, " ")
      .replace(/:$/, "")
      .trim();

  const remember = (line: string): boolean => {
    const key = lineKey(line);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  };

  const flushParagraph = () => {
    if (!paragraphBuf.length) return;
    const joined = paragraphBuf.join(" ").trim();
    paragraphBuf = [];
    if (!remember(joined)) return;
    blocks.push({ type: "paragraph", text: joined });
  };

  const flushList = () => {
    if (!listBuf.length) return;
    const items = listBuf.filter((item) => remember(item));
    listBuf = [];
    if (!items.length) return;
    blocks.push({ type: "list", items });
  };

  const pushSection = (title: string) => {
    flushList();
    flushParagraph();
    const cleaned = title.replace(/:$/, "").trim();
    if (remember(cleaned)) {
      blocks.push({ type: "section", title: cleaned });
    }
  };

  for (const rawLine of text.split(/\n/)) {
    const line = rawLine.trim();
    if (!line) {
      flushList();
      flushParagraph();
      continue;
    }

    const section = line.match(SECTION_RE);
    if (section) {
      pushSection(section[1]);
      continue;
    }

    if (SECTION_BARE_RE.test(line)) {
      pushSection(line);
      continue;
    }

    if (BULLET_RE.test(line)) {
      flushParagraph();
      listBuf.push(line.replace(BULLET_RE, "").trim());
      continue;
    }

    flushList();
    paragraphBuf.push(line);
  }

  flushList();
  flushParagraph();
  return blocks;
}
