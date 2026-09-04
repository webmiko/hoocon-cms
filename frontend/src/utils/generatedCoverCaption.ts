const ARTICLE_AI_COVER_SLUGS = new Set([
  "sertifikaty-ce-ul-eac-elektroprivody-ovk",
  "podbor-privoda-po-momentu-i-ploshchadi",
  "tipy-upravleniya-privodom",
  "pitanie-24-ili-230-v",
  "mu-mqu-hv-kogda-nuzhen-uskorennyy",
  "analog-belimo-hoocon",
  "suffiksy-d-a-s-t",
  "fu-vs-eu-fail-safe",
  "vspomogatelnyy-pereklyuchatel",
  "komplekt-sharovoy-kran-privod",
  "pasport-i-sertifikaty-v-zayavke",
]);

const NEWS_AI_COVER_SLUGS = new Set([
  "articles-podbor-i-sertifikaty",
]);

const AI_COVER_CAPTION =
  "Изображение сгенерировано ИИ. Возможны отличия от оригинального продукта";

export function generatedCoverCaption(
  kind: "article" | "news",
  slug: string | null | undefined,
): string | null {
  if (!slug) return null;
  if (kind === "article" && ARTICLE_AI_COVER_SLUGS.has(slug)) {
    return AI_COVER_CAPTION;
  }
  if (kind === "news" && NEWS_AI_COVER_SLUGS.has(slug)) {
    return AI_COVER_CAPTION;
  }
  return null;
}
