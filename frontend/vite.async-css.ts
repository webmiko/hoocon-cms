import type { Plugin } from "vite";

/** Keep in sync with ``src/hooconMainCss.ts``. */
const MAIN_CSS_ID = "hoocon-main-css";

/**
 * Make Vite entry CSS non-blocking for Lighthouse (media=print until JS).
 *
 * Inline ``onload`` is blocked by CSP ``script-src`` without unsafe-inline;
 * ``main.tsx`` promotes the sheet to ``media="all"`` instead.
 */
export function asyncEntryCssPlugin(): Plugin {
  return {
    name: "hoocon-async-entry-css",
    apply: "build",
    enforce: "post",
    transformIndexHtml(html) {
      return html.replace(
        /<link\s+rel="stylesheet"([^>]*?)href="([^"]+\.css)"([^>]*)\/?>/gi,
        (_full, before: string, href: string, after: string) => {
          const attrs = `${before}${after}`.replace(/\s+/g, " ").trim();
          const extra = attrs ? ` ${attrs}` : "";
          return (
            `<link rel="preload" as="style"${extra} href="${href}">` +
            `<link rel="stylesheet"${extra} href="${href}" media="print" ` +
            `id="${MAIN_CSS_ID}">`
          );
        },
      );
    },
  };
}
