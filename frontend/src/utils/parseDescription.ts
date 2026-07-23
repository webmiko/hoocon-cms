/** Parse catalog description (lead + bullets + section titles) into semantic HTML. */

const BULLET_RE = /^[–—\-•·*]\s+/;
/** Soft-wrapped continuation of a previous ``–`` line (ETL / 119-char wrap). */
const LIST_WRAP_INDENT_RE = /^[ \t]{2,}\S/;
/** Strip decorative markers before matching section titles (``✅ Преимущества``). */
const TITLE_DECOR_RE = /^[✅⚠❗●•]\s*/;
/** ``Основные особенности:`` or colon-less titles like ``Преимущества``. */
const SECTION_RE = /^(.{2,120}):\s*$/;
/** Major marketing / series sections → h2. */
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
    "назначение и принцип работы|" +
    "требования безопасности и эксплуатации|" +
    "особенности восстановления после пожара|" +
    "заключение|" +
    "общие характеристики аналогов|" +
    "преимущества серии(?:\\s.+)?" +
    ")$",
  "i",
);
/** Known bare subsections (no trailing colon in source) → h3. */
const SECTION_SUB_BARE_RE = new RegExp(
  "^(" +
    "промышленные объекты|общественные здания|специальные сооружения|" +
    "интеграция|температурный режим|класс защиты|уровень шума|" +
    "особенности(?:\\s+приводов)?|вспомогательные компоненты|запреты" +
    ")$",
  "i",
);

export type InstructionSectionLevel = 2 | 3 | 4;

export type DescriptionBlock =
  | { type: "paragraph"; text: string }
  | { type: "section"; title: string; level?: InstructionSectionLevel }
  | { type: "list"; items: string[] };

/** ``3.1 …``, ``7.2 …`` — вложенный подпункт (h3 under numbered h2). */
const INSTRUCTION_NESTED_RE = /^\d+\.\d+(?:\.\d+)*\s+/;
/** ``1. …``, ``10. …`` — глава инструкции (h2). */
const INSTRUCTION_CHAPTER_RE = /^\d+\.\s+(?!\d)/;
/** Intro line «Инструкция…» — lead/quote, not a heading. */
const INSTRUCTION_INTRO_RE = /^инструкция(?:\s|$)/i;

/**
 * Detect semantic heading level for install/control instruction lines.
 *
 * Hierarchy (outline):
 * - ``2`` — numbered chapter ``1.``, ``2.``, …
 * - ``3`` — subsection under a chapter (``Проверка совместимости``, ``3.1 …``)
 * - ``4`` — reserved for deeper nesting (unused in current copy)
 *
 * The document intro ``Инструкция…`` stays a paragraph (quote), not a heading.
 *
 * Returns:
 * - ``2`` / ``3`` / ``4`` or ``null`` when the line is not a heading.
 */
export function instructionHeadingLevel(line: string): InstructionSectionLevel | null {
  const trimmed = line.trim();
  if (!trimmed) return null;
  if (INSTRUCTION_NESTED_RE.test(trimmed)) return 3;
  if (INSTRUCTION_CHAPTER_RE.test(trimmed)) return 2;
  return null;
}

/**
 * Connective / sentence-lead titles that must not become headings
 * (``Например:``, ``Режимы:``, ``Привод предназначен для использования в:``).
 */
const WEAK_CONNECTIVE_RE = new RegExp(
  "^(" +
    "например|режимы|диапазон напряжения для|" +
    "привод предназначен для использования в" +
    ")$",
  "i",
);

/** Numbered marketing feature ``1. Крутящий момент`` (not ``1.1`` nested). */
const NUMBERED_FEATURE_RE = /^\d+\.\s+(?!\d).{2,80}$/;

/** Normalize a title line for regex matching (drop colon / emoji). */
function cleanTitle(line: string): string {
  return line.replace(TITLE_DECOR_RE, "").replace(/:$/, "").trim();
}

/**
 * True when ``rawLine`` continues the previous list item (soft line wrap).
 *
 * Prefer source indent (``  continuation``). Also join lowercase / ``(`` leads
 * when the previous item looks unfinished. Never swallow headings / chapters.
 */
export function isListItemContinuation(
  rawLine: string,
  prevItem: string,
): boolean {
  if (!prevItem.trim()) return false;

  const line = rawLine.replace(/\u200b/g, "").trim();
  if (!line || BULLET_RE.test(line)) return false;
  if (INSTRUCTION_NESTED_RE.test(line) || INSTRUCTION_CHAPTER_RE.test(line)) {
    return false;
  }
  if (INSTRUCTION_INTRO_RE.test(line)) return false;
  if (SECTION_RE.test(line)) return false;
  const bare = cleanTitle(line);
  if (SECTION_BARE_RE.test(bare) || SECTION_SUB_BARE_RE.test(bare)) {
    return false;
  }

  if (LIST_WRAP_INDENT_RE.test(rawLine)) return true;

  const prev = prevItem.trim();
  if (/[,;]$/.test(prev)) return true;
  if (/^[a-zа-яё(«"']/.test(line)) return true;
  return false;
}

/**
 * Parse category install instructions with h2/h3/h4 section levels.
 *
 * Reclassifies numbered chapter lines that ``parseDescription`` would emit
 * as plain paragraphs into section blocks with ``level``. Colon-only titles
 * (``Проверка совместимости:``) become h3 subsections. Intro ``Инструкция…``
 * remains a lead paragraph. Weak connective colon-lines stay paragraphs.
 *
 * Under a numbered h2 (``1. …``), bare h3 titles inherit ``1.1``, ``1.2``, …
 * Existing ``3.1``-style titles are kept as-is.
 */
export function parseInstructions(raw: string): DescriptionBlock[] {
  const leveled = parseDescription(raw).map((block) => {
    if (block.type === "section") {
      if (WEAK_CONNECTIVE_RE.test(cleanTitle(block.title))) {
        return { type: "paragraph" as const, text: block.title };
      }
      return { ...block, level: instructionHeadingLevel(block.title) ?? 3 };
    }
    if (block.type === "paragraph") {
      const level = instructionHeadingLevel(block.text);
      if (level !== null) {
        return { type: "section" as const, title: block.text, level };
      }
    }
    return block;
  });
  return numberInstructionSubsections(leveled);
}

const CHAPTER_NUM_RE = /^(\d+)\.\s+(?!\d)/;
const NESTED_NUM_RE = /^(\d+)\.(\d+)(?:\.\d+)*\s+/;

/**
 * Prefix bare h3 titles with ``N.M`` under the current numbered h2 chapter.
 *
 * Args:
 *   blocks: Blocks already tagged with ``level`` 2/3/4.
 *
 * Returns:
 *   New block list; h2 and pre-numbered ``3.1`` titles unchanged.
 */
export function numberInstructionSubsections(
  blocks: DescriptionBlock[],
): DescriptionBlock[] {
  let chapter: number | null = null;
  let sub = 0;
  const out: DescriptionBlock[] = [];

  for (const block of blocks) {
    if (block.type !== "section") {
      out.push(block);
      continue;
    }

    const level = block.level ?? 3;
    const title = block.title.trim();

    if (level === 2) {
      const m = title.match(CHAPTER_NUM_RE);
      chapter = m ? Number(m[1]) : null;
      sub = 0;
      out.push(block);
      continue;
    }

    if (level === 3 && chapter !== null) {
      if (NESTED_NUM_RE.test(title)) {
        const nested = title.match(NESTED_NUM_RE);
        if (nested) {
          sub = Math.max(sub, Number(nested[2]));
        }
        out.push(block);
        continue;
      }
      sub += 1;
      const bare = cleanTitle(title).replace(CHAPTER_NUM_RE, "").trim();
      out.push({
        ...block,
        title: `${chapter}.${sub} ${bare}`,
      });
      continue;
    }

    out.push(block);
  }

  return out;
}

/**
 * Detect semantic heading level for product/marketing description titles.
 *
 * Hierarchy (outline under page h1):
 * - ``2`` — major sections (``Ключевые характеристики``, ``Области применения``)
 * - ``3`` — numbered features and known/minor subheads (``1. …``, ``Класс защиты``)
 * - ``null`` — connective leads (``Например``) — stay as paragraphs
 */
export function descriptionHeadingLevel(line: string): InstructionSectionLevel | null {
  const cleaned = cleanTitle(line);
  if (!cleaned || BULLET_RE.test(cleaned)) return null;
  if (WEAK_CONNECTIVE_RE.test(cleaned)) return null;
  if (INSTRUCTION_NESTED_RE.test(cleaned)) return 4;
  if (NUMBERED_FEATURE_RE.test(cleaned)) return 3;
  if (SECTION_BARE_RE.test(cleaned)) return 2;
  if (SECTION_SUB_BARE_RE.test(cleaned)) return 3;
  return 3;
}

/**
 * Parse product/marketing description with h2 majors and h3 features.
 *
 * Demotes weak connective titles to paragraphs; promotes numbered
 * ``1. Title`` lines and known bare subheads that ``parseDescription``
 * left as paragraphs. Drops empty sections (heading with no body).
 */
export function parseProductDescription(raw: string): DescriptionBlock[] {
  const out: DescriptionBlock[] = [];
  for (const block of parseDescription(raw)) {
    if (block.type === "section") {
      const level = descriptionHeadingLevel(block.title);
      if (level === null) {
        out.push({ type: "paragraph", text: block.title });
        continue;
      }
      out.push({ ...block, title: cleanTitle(block.title), level });
      continue;
    }
    if (block.type === "paragraph") {
      const rawText = block.text.trim();
      const cleaned = cleanTitle(rawText);
      const level = descriptionHeadingLevel(cleaned);
      if (
        level !== null &&
        (NUMBERED_FEATURE_RE.test(cleaned) ||
          SECTION_BARE_RE.test(cleaned) ||
          SECTION_SUB_BARE_RE.test(cleaned))
      ) {
        out.push({ type: "section", title: cleaned, level });
        continue;
      }
    }
    out.push(block);
  }
  return dropEmptySections(out);
}

/** Remove empty h3/h4 sections (no body before next section / EOF). Keep h2 group titles. */
function dropEmptySections(blocks: DescriptionBlock[]): DescriptionBlock[] {
  const out: DescriptionBlock[] = [];
  for (let i = 0; i < blocks.length; i++) {
    const block = blocks[i];
    if (block.type === "section" && (block.level ?? 3) >= 3) {
      const next = blocks[i + 1];
      if (!next || next.type === "section") {
        continue;
      }
    }
    out.push(block);
  }
  return out;
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
      .replace(TITLE_DECOR_RE, "")
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
    const cleaned = cleanTitle(title);
    if (remember(cleaned)) {
      blocks.push({ type: "section", title: cleaned });
    }
  };

  for (const rawLine of text.split(/\n/)) {
    const line = rawLine.replace(/\u200b/g, "").trim();
    if (!line) {
      flushList();
      flushParagraph();
      continue;
    }

    // Soft-wrapped bullet continuation (``– foo,\n  bar``) stays one list item.
    if (
      listBuf.length > 0 &&
      isListItemContinuation(rawLine.replace(/\u200b/g, ""), listBuf[listBuf.length - 1])
    ) {
      const last = listBuf.length - 1;
      listBuf[last] = `${listBuf[last]} ${line}`.replace(/\s+/g, " ").trim();
      continue;
    }

    // Bullets before section titles — «– Убедитесь…:» is a list item, not h2.
    if (BULLET_RE.test(line)) {
      flushParagraph();
      listBuf.push(line.replace(BULLET_RE, "").trim());
      continue;
    }

    // «Инструкция…» intro stays its own lead paragraph (quote), never merges with
    // the following description line when the source omits a blank line.
    if (INSTRUCTION_INTRO_RE.test(line)) {
      flushList();
      flushParagraph();
      if (remember(line)) {
        blocks.push({ type: "paragraph", text: line });
      }
      continue;
    }

    const section = line.match(SECTION_RE);
    if (section) {
      pushSection(section[1]);
      continue;
    }

    const bare = cleanTitle(line);
    if (SECTION_BARE_RE.test(bare) || SECTION_SUB_BARE_RE.test(bare)) {
      pushSection(bare);
      continue;
    }

    flushList();
    paragraphBuf.push(line);
  }

  flushList();
  flushParagraph();
  return blocks;
}
