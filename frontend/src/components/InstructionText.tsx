import { SoftBreakText } from "./SoftBreakText";
import {
  parseInstructions,
  type DescriptionBlock,
  type InstructionSectionLevel,
} from "../utils/parseDescription";

export type InstructionTextStyles = {
  lead: string;
  quote?: string;
  docTitle: string;
  section: string;
  subsection: string;
  list: string;
};

type InstructionTextProps = {
  text: string;
  styles: InstructionTextStyles;
  /** Defaults to install-instruction parser (numbered chapters → h2). */
  parse?: (raw: string) => DescriptionBlock[];
};

function sectionClassName(
  level: InstructionSectionLevel,
  styles: InstructionTextStyles,
): string {
  if (level === 2) return styles.docTitle;
  if (level === 4) return styles.subsection;
  return styles.section;
}

function isInstructionIntro(text: string): boolean {
  return /^инструкция(?:\s|$)/i.test(text.trim());
}

function InstructionBlock({
  block,
  styles,
}: {
  block: DescriptionBlock;
  styles: InstructionTextStyles;
}) {
  if (block.type === "paragraph") {
    if (isInstructionIntro(block.text) && styles.quote) {
      return (
        <blockquote className={styles.quote}>
          <SoftBreakText text={block.text} />
        </blockquote>
      );
    }
    return (
      <p className={styles.lead}>
        <SoftBreakText text={block.text} />
      </p>
    );
  }
  if (block.type === "section") {
    const level = block.level ?? 3;
    const Tag = level === 2 ? "h2" : level === 4 ? "h4" : "h3";
    return (
      <Tag className={sectionClassName(level, styles)}>
        <SoftBreakText text={block.title} />
      </Tag>
    );
  }
  return (
    <ul className={styles.list}>
      {block.items.map((item) => (
        <li key={item}>
          <SoftBreakText text={item} />
        </li>
      ))}
    </ul>
  );
}

/** Render structured plain text with h2/h3/h4 from ``parse`` (default: instructions). */
export function InstructionText({
  text,
  styles,
  parse = parseInstructions,
}: InstructionTextProps) {
  return parse(text).map((block, index) => (
    <InstructionBlock key={index} block={block} styles={styles} />
  ));
}
