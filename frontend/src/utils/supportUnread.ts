/** Visitor unread counter for the support widget (closed panel). */

export const SUPPORT_LAST_READ_KEY = "hoocon-support-last-read-id";

export function readSupportLastReadId(): number {
  try {
    const raw = sessionStorage.getItem(SUPPORT_LAST_READ_KEY);
    if (!raw) return 0;
    const parsed = Number.parseInt(raw, 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
  } catch {
    return 0;
  }
}

export function writeSupportLastReadId(id: number): void {
  if (!Number.isFinite(id) || id <= 0) return;
  try {
    sessionStorage.setItem(SUPPORT_LAST_READ_KEY, String(id));
  } catch {
    /* private mode */
  }
}

export function maxSupportMessageId(
  messages: Array<{ id: number }>,
  fallback = 0,
): number {
  if (!messages.length) return fallback;
  return Math.max(fallback, ...messages.map((m) => m.id));
}

/** Staff / bot replies the visitor has not opened yet. */
export function countSupportUnread(
  messages: Array<{ id: number; direction: string }>,
  lastReadId: number,
): number {
  return messages.filter(
    (m) => m.id > lastReadId && m.direction !== "inbound",
  ).length;
}
