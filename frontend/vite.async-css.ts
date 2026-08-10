import type { Plugin } from "vite";

/** Keep in sync with ``src/hooconMainCss.ts``. */
const MAIN_CSS_ID = "hoocon-main-css";

/**
 * Make Vite entry CSS non-blocking for Lighthouse (media=print until JS).
 *
 * Per Chrome render-blocking guidance: defer CSS not needed for first paint
 * (https://developer.chrome.com/docs/performance/insights/render-blocking).
 * Inline ``onload`` is blocked by CSP; ``main.tsx`` sets ``media="all"``.
 *
 * Must run after VitePWA's HTML transform (register this plugin last).
 */
export function asyncEntryCssPlugin(): Plugin {
  return {
    name: "hoocon-async-entry-css",
    apply: "build",
    enforce: "post",
    transformIndexHtml: {
      order: "post",
      handler(html) {
        // Idempotent: skip links already deferred.
        if (html.includes(`id="${MAIN_CSS_ID}"`)) {
          return html;
        }
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
    },
  };
}
