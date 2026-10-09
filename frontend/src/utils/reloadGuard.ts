/**
 * Single gate for release reloads (SW update + /api/health/ version check).
 *
 * A deploy must not wipe a half-typed RFQ, chat message or cabinet form:
 * the reload waits until every text field the visitor touched is empty
 * again (sent, cleared, or unmounted by navigation).
 */

const FIELD_SELECTOR = [
  "textarea",
  "input:not([type])",
  'input[type="text"]',
  'input[type="email"]',
  'input[type="tel"]',
  'input[type="number"]',
  '[contenteditable="true"]',
].join(", ");

export const RELOAD_RETRY_MS = 30_000;

function fieldValue(el: Element): string {
  if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
    return el.value;
  }
  return el.textContent ?? "";
}

export function createReloadGuard(doc: Document = document, win: Window = window) {
  let typed = false;
  let pending = false;

  doc.addEventListener(
    "input",
    (event) => {
      const target = event.target;
      if (target instanceof Element && target.matches(FIELD_SELECTOR)) {
        typed = true;
      }
    },
    true,
  );

  /** True while a field holds text and the visitor has typed on this page. */
  function hasUnsavedInput(): boolean {
    if (!typed) return false;
    for (const el of doc.querySelectorAll(FIELD_SELECTOR)) {
      if (fieldValue(el).trim()) return true;
    }
    typed = false;
    return false;
  }

  /** Reload now if safe, otherwise retry on tab hide and every RELOAD_RETRY_MS. */
  function requestReload(reload: () => void = () => win.location.reload()): void {
    if (pending) return;
    pending = true;
    let timer: number | undefined = undefined;

    const onVisibility = () => {
      attempt();
    };
    function attempt(): void {
      if (hasUnsavedInput()) return;
      if (timer !== undefined) win.clearInterval(timer);
      doc.removeEventListener("visibilitychange", onVisibility);
      reload();
    }

    if (!hasUnsavedInput()) {
      reload();
      return;
    }
    timer = win.setInterval(attempt, RELOAD_RETRY_MS);
    doc.addEventListener("visibilitychange", onVisibility);
  }

  return { hasUnsavedInput, requestReload };
}

let shared: ReturnType<typeof createReloadGuard> | null = null;

/** App-wide guard; created lazily so tests and SSR-free imports stay inert. */
export function reloadGuard(): ReturnType<typeof createReloadGuard> {
  shared ??= createReloadGuard();
  return shared;
}
