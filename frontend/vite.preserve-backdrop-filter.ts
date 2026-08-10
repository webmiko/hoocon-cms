import type { Plugin } from "vite";

/**
 * LightningCSS minify (Vite default) may drop unprefixed ``backdrop-filter``
 * when ``-webkit-backdrop-filter`` is also present, keeping only the prefix.
 * Firefox ignores ``-webkit-*`` → frosted glass looks nearly opaque on prod
 * while Vite dev (no minify) still shows full blur.
 *
 * Restore the standard property next to any lone ``-webkit-backdrop-filter``.
 */
export function preserveBackdropFilterPlugin(): Plugin {
  return {
    name: "hoocon-preserve-backdrop-filter",
    apply: "build",
    enforce: "post",
    generateBundle(_options, bundle) {
      for (const item of Object.values(bundle)) {
        if (item.type !== "asset" || !item.fileName.endsWith(".css")) {
          continue;
        }
        const source =
          typeof item.source === "string"
            ? item.source
            : Buffer.isBuffer(item.source)
              ? item.source.toString("utf8")
              : null;
        if (!source || !source.includes("-webkit-backdrop-filter:")) {
          continue;
        }
        const next = source.replace(/\{[^}]*\}/g, (block) => {
          if (!block.includes("-webkit-backdrop-filter:")) {
            return block;
          }
          if (/(?<!-webkit-)backdrop-filter:/.test(block)) {
            return block;
          }
          return block.replace(
            /-webkit-backdrop-filter:([^;]+);/,
            "-webkit-backdrop-filter:$1;backdrop-filter:$1;",
          );
        });
        if (next !== source) {
          item.source = next;
        }
      }
    },
  };
}
