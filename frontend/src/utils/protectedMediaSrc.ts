/**
 * Session cache: real media path → blob: URL for display in product UI.
 *
 * Hides ``/media/...`` from ``img.src`` / Inspect Element. Network tab still
 * shows the fetch URL — that cannot be removed if the browser must load bytes.
 */

const blobBySrc = new Map<string, string>();
const inflight = new Map<string, Promise<string>>();

function isAlreadyOpaque(src: string): boolean {
  return src.startsWith("blob:") || src.startsWith("data:");
}

/**
 * Synchronous lookup of a session-cached display URL (no network).
 *
 * Args:
 *   src: Media path previously resolved via ``resolveProtectedMediaSrc``.
 *
 * Returns:
 *   Cached ``blob:`` / opaque URL, or ``null`` if not yet in the session cache.
 */
export function peekProtectedMediaSrc(src: string): string | null {
  const trimmed = src.trim();
  if (!trimmed) {
    return null;
  }
  if (isAlreadyOpaque(trimmed)) {
    return trimmed;
  }
  return blobBySrc.get(trimmed) ?? null;
}

/**
 * Resolve a display URL that does not expose the storage path in ``img.src``.
 *
 * Args:
 *   src: Root-relative or absolute media URL (e.g. ``/media/product_images/...``).
 *
 * Returns:
 *   ``blob:`` object URL (cached for the session), or ``src`` when already opaque.
 *
 * Raises:
 *   Error when the fetch fails (caller may fall back to ``src``).
 */
export async function resolveProtectedMediaSrc(src: string): Promise<string> {
  const trimmed = src.trim();
  if (!trimmed) {
    throw new Error("empty media src");
  }
  if (isAlreadyOpaque(trimmed)) {
    return trimmed;
  }

  const cached = blobBySrc.get(trimmed);
  if (cached) {
    return cached;
  }

  let pending = inflight.get(trimmed);
  if (!pending) {
    pending = fetch(trimmed, {
      credentials: "same-origin",
      mode: "same-origin",
      // Prefer cache so catalog wash + display share one network hit.
      cache: "force-cache",
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`media fetch ${response.status}`);
        }
        const blob = await response.blob();
        if (
          !blob.type.startsWith("image/") &&
          blob.type !== "application/octet-stream"
        ) {
          // Some servers omit type; still try Object URL for known image paths.
          if (!trimmed.includes("/media/")) {
            throw new Error(`unexpected media type: ${blob.type || "empty"}`);
          }
        }
        const objectUrl = URL.createObjectURL(blob);
        blobBySrc.set(trimmed, objectUrl);
        return objectUrl;
      })
      .finally(() => {
        inflight.delete(trimmed);
      });
    inflight.set(trimmed, pending);
  }

  return pending;
}

/** Test helper: clear session blob cache. */
export function clearProtectedMediaSrcCacheForTests(): void {
  for (const url of blobBySrc.values()) {
    URL.revokeObjectURL(url);
  }
  blobBySrc.clear();
  inflight.clear();
}
