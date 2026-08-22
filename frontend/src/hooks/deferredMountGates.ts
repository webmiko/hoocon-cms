/** Pure gates for ``useDeferredMount`` (unit-tested without jsdom). */

export function locationHashMatches(
  hashIds: readonly string[] | undefined,
  locationHash: string,
): boolean {
  if (!hashIds?.length) {
    return false;
  }
  const h = locationHash.replace(/^#/, "");
  return hashIds.includes(h);
}

export function scrollGateSatisfied(
  requireScrollPx: number | undefined,
  scrolled: boolean,
  hashHit: boolean,
): boolean {
  if (requireScrollPx === undefined) {
    return true;
  }
  return scrolled || hashHit;
}
