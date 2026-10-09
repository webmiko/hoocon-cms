/**
 * Head tags that ``<Seo>`` renders per route. The server bakes the same tags
 * into index.html for crawlers; React 19 hoists Helmet's copies next to them
 * instead of replacing, so the static ones must go before the first render.
 * JSON-LD stays: some blocks exist only server-side.
 */
export const SERVER_SEO_SELECTOR = [
  'link[rel="canonical"]',
  'link[rel="alternate"][hreflang]',
  'meta[name="description"]',
  'meta[name="robots"]',
  'meta[property^="og:"]',
  'meta[name^="twitter:"]',
].join(", ");

export function removeServerSeoTags(head: ParentNode = document.head): number {
  const nodes = Array.from(head.querySelectorAll(SERVER_SEO_SELECTOR));
  for (const node of nodes) {
    node.remove();
  }
  return nodes.length;
}
