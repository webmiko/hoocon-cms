import { SoftBreakText } from "./SoftBreakText";
import {
  parseInstructions,
  type DescriptionBlock,
  type InstructionSectionLevel,
} from "../utils/parseDescription";

export type InstructionTextStyles = {
  lead: string;
  docTitle: string;
  section: string;
  subsection: string;
  list: string;
};

type InstructionTextProps = {
  text: string;
  styles: InstructionTextStyles;
};

function sectionClassName(
  level: InstructionSectionLevel,
  styles: InstructionTextStyles,
): string {
  if (level === 2) return styles.docTitle;
  if (level === 4) return styles.subsection;
  return styles.section;
}

function InstructionBlock({
  block,
  styles,
}: {
  block: DescriptionBlock;
  styles: InstructionTextStyles;
}) {
  if (block.type === "paragraph") {
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

/** Render category install instructions with h2/h3/h4 heading hierarchy. */
export function InstructionText({ text, styles }: InstructionTextProps) {
  return parseInstructions(text).map((block, index) => (
    <InstructionBlock key={index} block={block} styles={styles} />
  ));
}
