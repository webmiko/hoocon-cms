/** Light reword of PDP hero lead for the Описание tab (SEO-safe). */

/**
 * Paraphrase a hero lead so the description tab is not an exact duplicate.
 *
 * Mirrors ``catalog.facets.copy.paraphrase_sku_lead`` on the backend.
 *
 * Args:
 *   lead: Hero blurb under H1.
 *
 * Returns:
 *   Reworded copy, or empty string when ``lead`` is blank.
 */
export function paraphraseSkuLead(lead: string): string {
  const text = lead.replace(/\s+/g, " ").trim().replace(/[.\s]+$/, "");
  if (!text) return "";

  const match = text.match(
    /^(?:электро)?привод\s+(.+?)\s+для\s+(.+?)(?:\s+с\s+(.+))?$/i,
  );
  if (match) {
    const head = match[1].trim();
    const purpose = match[2].trim();
    const withFeat = (match[3] || "").trim();
    const bits = [`Применяется для ${purpose}`];
    if (withFeat) bits.push(`в исполнении с ${withFeat}`);
    const first = `${bits.join("; ")}.`;
    if (/\d/.test(head)) {
      return `${first} Номинальный крутящий момент — ${head}.`;
    }
    const rest = head ? head[0].toUpperCase() + head.slice(1) : "";
    return rest ? `${first} ${rest}.` : first;
  }

  const body = text[0].toLowerCase() + text.slice(1);
  return `Назначение модели: ${body}.`;
}
