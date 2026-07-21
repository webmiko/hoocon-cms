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

export type InstructionSectionLevel = 2 | 3 | 4;

export type DescriptionBlock =
  | { type: "paragraph"; text: string }
  | { type: "section"; title: string; level?: InstructionSectionLevel }
  | { type: "list"; items: string[] };

/** ``3.1 …``, ``7.2 …`` — подраздел инструкции (h4). */
const INSTRUCTION_H4_RE = /^\d+\.\d+(?:\.\d+)*\s+/;
/** ``1. …``, ``10. …`` — раздел инструкции (h3). */
const INSTRUCTION_H3_RE = /^\d+\.\s+(?!\d)/;
/** Документ без нумерации, напр. «Инструкция по установке…» (h2). */
const INSTRUCTION_H2_RE = /^инструкция\b/i;

/**
 * Detect semantic heading level for install/control instruction lines.
 *
 * Returns:
 * - ``2`` — document title (no chapter number)
 * - ``3`` — top-level numbered sections ``1.``, ``2.``, …
 * - ``4`` — nested sections ``3.1``, ``4.2``, …
 */
export function instructionHeadingLevel(line: string): InstructionSectionLevel | null {
  const trimmed = line.trim();
  if (!trimmed) return null;
  if (INSTRUCTION_H4_RE.test(trimmed)) return 4;
  if (INSTRUCTION_H3_RE.test(trimmed)) return 3;
  if (INSTRUCTION_H2_RE.test(trimmed)) return 2;
  return null;
}

/**
 * Parse category install instructions with h2/h3/h4 section levels.
 *
 * Reclassifies numbered chapter lines that ``parseDescription`` would emit
 * as plain paragraphs into section blocks with ``level``.
 */
export function parseInstructions(raw: string): DescriptionBlock[] {
  return parseDescription(raw).map((block) => {
    if (block.type === "section") {
      return { ...block, level: instructionHeadingLevel(block.title) ?? 2 };
    }
    if (block.type === "paragraph") {
      const level = instructionHeadingLevel(block.text);
      if (level !== null) {
        return { type: "section" as const, title: block.text, level };
      }
    }
    return block;
  });
}

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
