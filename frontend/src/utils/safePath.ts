/**
 * Same-origin path for push clicks / ``next`` (open-redirect guard).
 *
 * String checks miss ``/\evil.com`` and ``/\t/evil.com`` — browsers read
 * both as ``//evil.com`` — so the URL is resolved the way the browser would.
 */
export function safeSameOriginPath(raw: unknown, origin: string, fallback = "/"): string {
  if (typeof raw !== "string") return fallback;
  const value = raw.trim();
  if (!value.startsWith("/")) return fallback;
  let url: URL;
  try {
    url = new URL(value, origin);
  } catch {
    return fallback;
  }
  if (url.origin !== new URL(origin).origin) return fallback;
  return `${url.pathname}${url.search}${url.hash}`.slice(0, 500);
}
