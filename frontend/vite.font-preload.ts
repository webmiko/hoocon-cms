import type { IndexHtmlTransformContext, Plugin } from "vite";

/** LCP body + hero display — cyrillic only (ru-RU primary). */
export const CRITICAL_FONT_FILE_RE =
  /(?:ibm-plex-sans-cyrillic-400-normal|montserrat-cyrillic-700-normal).*\.woff2$/;

export function criticalFontPreloadHrefs(
  bundle: Record<string, unknown>,
): string[] {
  return Object.keys(bundle)
    .filter((name) => CRITICAL_FONT_FILE_RE.test(name))
    .sort()
    .map((name) => (name.startsWith("/") ? name : `/${name}`));
}

export function fontPreloadPlugin(): Plugin {
  return {
    name: "hoocon-font-preload",
    apply: "build",
    enforce: "post",
    transformIndexHtml: {
      order: "post",
      handler(html: string, ctx: IndexHtmlTransformContext) {
        if (!ctx.bundle) {
          return html;
        }
        const hrefs = criticalFontPreloadHrefs(ctx.bundle);
        if (!hrefs.length) {
          return html;
        }
        const marker = 'rel="preload" as="font"';
        if (html.includes(marker)) {
          return html;
        }
        const tags = hrefs
          .map(
            (href) =>
              `<link rel="preload" href="${href}" as="font" type="font/woff2" crossorigin>`,
          )
          .join("\n    ");
        return html.replace("</head>", `    ${tags}\n  </head>`);
      },
    },
  };
}
