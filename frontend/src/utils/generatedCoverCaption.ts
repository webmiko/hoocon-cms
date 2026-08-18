const ARTICLE_AI_COVER_SLUGS = new Set([
  "sertifikaty-ce-ul-eac-elektroprivody-ovk",
  "podbor-privoda-po-momentu-i-ploshchadi",
  "tipy-upravleniya-privodom",
  "pitanie-24-ili-230-v",
  "mu-mqu-hv-kogda-nuzhen-uskorennyy",
  "analog-belimo-hoocon",
]);

const NEWS_AI_COVER_SLUGS = new Set([
  "articles-podbor-i-sertifikaty",
]);

export function generatedCoverCaption(
  kind: "article" | "news",
  slug: string | null | undefined,
): string | null {
  if (!slug) return null;
  if (kind === "article" && ARTICLE_AI_COVER_SLUGS.has(slug)) {
    return "Изображение сгенерировано ИИ";
  }
  if (kind === "news" && NEWS_AI_COVER_SLUGS.has(slug)) {
    return "Изображение сгенерировано ИИ";
  }
  return null;
}
