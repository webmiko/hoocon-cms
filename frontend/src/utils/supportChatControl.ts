/**
 * Browser control for the floating support chat (show/hide widget, open panel).
 *
 * Console / bookmarklets:
 *   window.hooconChat.show()
 *   window.hooconChat.hide()
 *   window.hooconChat.open()
 *   window.hooconChat.close()
 *   window.hooconChat.toggle()
 *
 * URL (once on load, then stripped from the address bar):
 *   ?chat=1 | open | show  → show widget and open panel
 *   ?chat=0 | hide         → hide widget (FAB off)
 */

export const SUPPORT_CHAT_EVENT = "hoocon:support-chat";
export const SUPPORT_CHAT_VISIBLE_KEY = "hoocon.supportChat.visible";

export type SupportChatState = {
  /** Entire widget (FAB + panel) mounted/visible. */
  visible: boolean;
  /** Conversation panel open. */
  open: boolean;
};

type SupportChatListener = (state: SupportChatState) => void;

let state: SupportChatState = {
  visible: true,
  open: false,
};

const listeners = new Set<SupportChatListener>();

function readStoredVisible(): boolean {
  if (typeof localStorage === "undefined") return true;
  try {
    const raw = localStorage.getItem(SUPPORT_CHAT_VISIBLE_KEY);
    if (raw === null) return true;
    return raw !== "0" && raw !== "false";
  } catch {
    return true;
  }
}

function persistVisible(visible: boolean): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(SUPPORT_CHAT_VISIBLE_KEY, visible ? "1" : "0");
  } catch {
    /* private mode / quota */
  }
}

function emit(): void {
  for (const listener of listeners) listener(state);
  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new CustomEvent(SUPPORT_CHAT_EVENT, { detail: { ...state } }),
    );
  }
}

function setState(patch: Partial<SupportChatState>): SupportChatState {
  const next: SupportChatState = {
    visible: patch.visible ?? state.visible,
    open: patch.open ?? state.open,
  };
  if (!next.visible) next.open = false;
  if (next.visible === state.visible && next.open === state.open) return state;
  state = next;
  if (patch.visible !== undefined) persistVisible(next.visible);
  emit();
  return state;
}

export function getSupportChatState(): SupportChatState {
  return { ...state };
}

export function subscribeSupportChat(
  listener: SupportChatListener,
): () => void {
  listeners.add(listener);
  listener(state);
  return () => {
    listeners.delete(listener);
  };
}

export function showSupportChat(): SupportChatState {
  return setState({ visible: true });
}

export function hideSupportChat(): SupportChatState {
  return setState({ visible: false, open: false });
}

export function openSupportChat(): SupportChatState {
  return setState({ visible: true, open: true });
}

export function closeSupportChat(): SupportChatState {
  return setState({ open: false });
}

export function toggleSupportChat(): SupportChatState {
  if (!state.visible) return openSupportChat();
  return setState({ open: !state.open });
}

export function toggleSupportChatVisible(): SupportChatState {
  return state.visible ? hideSupportChat() : showSupportChat();
}

/** Sync panel open flag from the React widget (FAB click). */
export function setSupportChatOpen(open: boolean): SupportChatState {
  if (!state.visible && open) return openSupportChat();
  return setState({ open });
}

export type HooconChatApi = {
  show: () => SupportChatState;
  hide: () => SupportChatState;
  open: () => SupportChatState;
  close: () => SupportChatState;
  toggle: () => SupportChatState;
  toggleVisible: () => SupportChatState;
  getState: () => SupportChatState;
};

declare global {
  interface Window {
    hooconChat?: HooconChatApi;
  }
}

function parseChatQuery(raw: string | null): "open" | "hide" | "show" | null {
  if (raw === null) return null;
  const value = raw.trim().toLowerCase();
  if (value === "1" || value === "open" || value === "true") return "open";
  if (value === "0" || value === "hide" || value === "false") return "hide";
  if (value === "show") return "show";
  return null;
}

function applyChatQueryOnce(): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  const action = parseChatQuery(url.searchParams.get("chat"));
  if (!action) return;
  if (action === "open") openSupportChat();
  else if (action === "hide") hideSupportChat();
  else showSupportChat();
  url.searchParams.delete("chat");
  const next = `${url.pathname}${url.search}${url.hash}`;
  window.history.replaceState(window.history.state, "", next);
}

/** Call once from the SPA entry (after DOM is available). */
export function installSupportChatControl(): void {
  state = { visible: readStoredVisible(), open: false };
  window.hooconChat = {
    show: showSupportChat,
    hide: hideSupportChat,
    open: openSupportChat,
    close: closeSupportChat,
    toggle: toggleSupportChat,
    toggleVisible: toggleSupportChatVisible,
    getState: getSupportChatState,
  };
  applyChatQueryOnce();
  emit();
}
