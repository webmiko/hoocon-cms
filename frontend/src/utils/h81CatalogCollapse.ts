/** Collapse multi-edition Product cards to one catalog tile per Product. */

const H81_PRODUCT_SLUG_RE = /^h81(?:01|02|03|04|05|06|07|08|21|22)$/i;
const BRASS_DN_PRODUCT_SLUG_RE = /^8100-bv\d+$/i;
const Q8100_DN_PRODUCT_SLUG_RE = /^8100q-bv\d+$/i;
const H8205_LAV_PRODUCT_SLUG_RE = /^h8205-lav\d+[st]*$/i;
const DAMU_PRODUCT_SLUG_RE = /^privod-vozdushniy-bez-pruzhini-damu-\d+nm$/i;
const DAMQU_PRODUCT_SLUG_RE = /^privod-vozdushniy-da\d+mqu-\d+nm$/i;
const DAFU_PRODUCT_SLUG_RE = /^privod-vozdushniy-pruzhina-dafu-\d+nm$/i;
/** SAMU Nm only — not ``privod-dimoudaleniya-hvd-*f``. */
const SAMU_PRODUCT_SLUG_RE = /^privod-dimoudaleniya-\d+nm$/i;
const SAFU_PRODUCT_SLUG_RE = /^privod-protivopozharniy-\d+nm$/i;
const HVA_PRODUCT_SLUG_RE =
  /^privod-vozdushniy-hva-\d+nm$|^privod-vozdushniy-bez-pruzhini-uskorenniy-hva-q-\d+nm$|^privod-vozdushniy-kondensator-hva-\d+qx$/i;
const HVD_AIR_PRODUCT_SLUG_RE =
  /^privod-vozdushniy-hvd-(?:\d+nm|\d+q)$|^privod-vozdushniy-kondensator-hvd-\d+qx$/i;
const HVD_SMOKE_PRODUCT_SLUG_RE = /^privod-dimoudaleniya-hvd-\d+f$/i;

export function isH81FamilyProductSlug(productSlug: string | undefined | null): boolean {
  return H81_PRODUCT_SLUG_RE.test((productSlug || "").trim());
}

export function isBrassDnProductSlug(productSlug: string | undefined | null): boolean {
  return BRASS_DN_PRODUCT_SLUG_RE.test((productSlug || "").trim());
}

export function isQ8100DnProductSlug(productSlug: string | undefined | null): boolean {
  return Q8100_DN_PRODUCT_SLUG_RE.test((productSlug || "").trim());
}

export function isH8205LavProductSlug(productSlug: string | undefined | null): boolean {
  return H8205_LAV_PRODUCT_SLUG_RE.test((productSlug || "").trim());
}

export function isDamuFamilyProductSlug(productSlug: string | undefined | null): boolean {
  return DAMU_PRODUCT_SLUG_RE.test((productSlug || "").trim());
}

export function isDamquFamilyProductSlug(productSlug: string | undefined | null): boolean {
  return DAMQU_PRODUCT_SLUG_RE.test((productSlug || "").trim());
}

export function isDafuFamilyProductSlug(productSlug: string | undefined | null): boolean {
  return DAFU_PRODUCT_SLUG_RE.test((productSlug || "").trim());
}

export function isSamuFamilyProductSlug(productSlug: string | undefined | null): boolean {
  return SAMU_PRODUCT_SLUG_RE.test((productSlug || "").trim());
}

export function isSafuFamilyProductSlug(productSlug: string | undefined | null): boolean {
  return SAFU_PRODUCT_SLUG_RE.test((productSlug || "").trim());
}

export function isHvaFamilyProductSlug(productSlug: string | undefined | null): boolean {
  return HVA_PRODUCT_SLUG_RE.test((productSlug || "").trim());
}

export function isHvdFamilyProductSlug(productSlug: string | undefined | null): boolean {
  const slug = (productSlug || "").trim();
  return HVD_AIR_PRODUCT_SLUG_RE.test(slug) || HVD_SMOKE_PRODUCT_SLUG_RE.test(slug);
}

function isCollapsibleFamilyProductSlug(
  productSlug: string | undefined | null,
): boolean {
  return (
    isH81FamilyProductSlug(productSlug) ||
    isBrassDnProductSlug(productSlug) ||
    isQ8100DnProductSlug(productSlug) ||
    isH8205LavProductSlug(productSlug) ||
    isDamuFamilyProductSlug(productSlug) ||
    isDamquFamilyProductSlug(productSlug) ||
    isDafuFamilyProductSlug(productSlug) ||
    isSamuFamilyProductSlug(productSlug) ||
    isSafuFamilyProductSlug(productSlug) ||
    isHvaFamilyProductSlug(productSlug) ||
    isHvdFamilyProductSlug(productSlug)
  );
}

/**
 * Keep the first SKU of each family Product; leave other series unchanged.
 *
 * Families: H81 / brass / H8205 / DAMU / DAMQU / DAFU / SAMU / SAFU / HVA / HVD.
 *
 * Args:
 *   skus: Catalog list rows (already filtered/sorted by API).
 *
 * Returns:
 *   Deduped list for grid display.
 */
export function collapseH81CatalogSkus<
  T extends { slug: string; product_slug?: string | null },
>(skus: T[]): T[] {
  const seenFamilies = new Set<string>();
  const out: T[] = [];
  for (const sku of skus) {
    const productSlug = (sku.product_slug || "").trim().toLowerCase();
    if (isCollapsibleFamilyProductSlug(productSlug)) {
      if (seenFamilies.has(productSlug)) continue;
      seenFamilies.add(productSlug);
    }
    out.push(sku);
  }
  return out;
}
