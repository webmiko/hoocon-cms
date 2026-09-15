import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function listFocusable(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (node) => node.tabIndex !== -1 && !node.hasAttribute("disabled"),
  );
}

/**
 * Trap keyboard focus inside an open modal/dialog and restore focus on close.
 */
export function useFocusTrap(
  containerRef: RefObject<HTMLElement | null>,
  active: boolean,
): void {
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!active) {
      return;
    }
    const container = containerRef.current;
    if (!container) {
      return;
    }
    const trapRoot = container;

    previousFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;

    const focusables = listFocusable(trapRoot);
    focusables[0]?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Tab") {
        return;
      }
      const nodes = listFocusable(trapRoot);
      if (nodes.length === 0) {
        return;
      }
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
        return;
      }
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    trapRoot.addEventListener("keydown", onKeyDown);
    return () => {
      trapRoot.removeEventListener("keydown", onKeyDown);
      previousFocusRef.current?.focus();
    };
  }, [active, containerRef]);
}
