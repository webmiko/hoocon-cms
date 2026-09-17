import type { ReactNode } from "react";
import { Link } from "react-router-dom";

const FAQ_PATH_LABELS: Record<string, string> = {
  "/consultation": "консультация",
  "/gde-kupit": "где купить",
  "/kontakty": "контакты",
  "/dokumentaciya": "документация",
  "/catalog": "каталог",
  "/faq": "вопросы и ответы",
  "/zavod": "OEM · завод",
  "/company": "о компании",
  "/rfq": "запрос цены",
};

const FAQ_PATH_RE =
  /\/[a-z0-9][a-z0-9-]*(?:\/[a-z0-9][a-z0-9-]*)*(?:\?[^\s]+)?(?:#[a-z0-9-]+)?/gi;

function faqLinkLabel(href: string): string {
  const [path, query = ""] = href.split(/[?#]/, 2);
  if (path === "/dokumentaciya" && query) {
    const sku = new URLSearchParams(query).get("q");
    if (sku) {
      return `документация: ${sku}`;
    }
  }
  return FAQ_PATH_LABELS[path] ?? href;
}

export type FaqAnswerLinkProps = {
  className?: string;
  onNavigate?: () => void;
};

/** Turn FAQ answer text with ``/path`` tokens into inline router links. */
export function faqAnswerNodes(
  text: string,
  linkProps?: FaqAnswerLinkProps,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  const re = new RegExp(FAQ_PATH_RE.source, "gi");
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      nodes.push(text.slice(last, match.index));
    }
    const raw = match[0];
    const trailing = raw.match(/[.,;:!?)\]»"']+$/);
    const href = trailing ? raw.slice(0, -trailing[0].length) : raw;
    const suffix = trailing ? trailing[0] : "";
    nodes.push(
      <Link
        key={`faq-link-${match.index}`}
        to={href}
        className={linkProps?.className}
        onClick={linkProps?.onNavigate}
      >
        {faqLinkLabel(href)}
      </Link>,
    );
    if (suffix) {
      nodes.push(suffix);
    }
    last = match.index + raw.length;
  }
  if (last < text.length) {
    nodes.push(text.slice(last));
  }
  return nodes;
}
