import { beforeEach, describe, expect, it, vi } from "vitest";

function installBrowserGlobals(pathWithQuery = "/") {
  const store = new Map<string, string>();
  const localStorage: Storage = {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (key) => (store.has(key) ? store.get(key)! : null),
    key: (index) => [...store.keys()][index] ?? null,
    removeItem: (key) => {
      store.delete(key);
    },
    setItem: (key, value) => {
      store.set(key, value);
    },
  };

  let href = `http://localhost${pathWithQuery}`;
  const location = {
    get href() {
      return href;
    },
    get pathname() {
      return new URL(href).pathname;
    },
    get search() {
      return new URL(href).search;
    },
    get hash() {
      return new URL(href).hash;
    },
  };

  const history = {
    state: null as unknown,
    replaceState(_state: unknown, _title: string, url?: string) {
      if (typeof url === "string") {
        href = new URL(url, "http://localhost").href;
      }
    },
  };

  type WinListener = (event: Event) => void;
  const listeners = new Map<string, WinListener[]>();

  const win = {
    localStorage,
    location,
    history,
    hooconChat: undefined as unknown,
    dispatchEvent(event: Event) {
      const set = listeners.get(event.type);
      if (set) for (const fn of set) fn(event);
      return true;
    },
    addEventListener(type: string, fn: WinListener) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type)!.push(fn);
    },
    removeEventListener(type: string, fn: WinListener) {
      const set = listeners.get(type);
      if (!set) return;
      const i = set.indexOf(fn);
      if (i >= 0) set.splice(i, 1);
    },
  };

  vi.stubGlobal("window", win);
  vi.stubGlobal("localStorage", localStorage);
  return win;
}

describe("supportChatControl", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
  });

  it("installs window.hooconChat show/hide/open/close", async () => {
    const win = installBrowserGlobals("/");
    const mod = await import("./supportChatControl");
    mod.installSupportChatControl();
    expect(win.hooconChat).toBeDefined();
    expect(mod.getSupportChatState()).toEqual({
      visible: true,
      open: false,
      unread: 0,
    });

    (win.hooconChat as { open: () => void }).open();
    expect(mod.getSupportChatState()).toEqual({
      visible: true,
      open: true,
      unread: 0,
    });

    (win.hooconChat as { hide: () => void }).hide();
    expect(mod.getSupportChatState()).toEqual({
      visible: false,
      open: false,
      unread: 0,
    });
    expect(localStorage.getItem(mod.SUPPORT_CHAT_VISIBLE_KEY)).toBe("0");

    (win.hooconChat as { show: () => void }).show();
    expect(mod.getSupportChatState().visible).toBe(true);
    expect(localStorage.getItem(mod.SUPPORT_CHAT_VISIBLE_KEY)).toBe("1");

    (win.hooconChat as { close: () => void }).close();
    expect(mod.getSupportChatState().open).toBe(false);
  });

  it("applies ?chat=1 once and strips the query", async () => {
    const win = installBrowserGlobals("/catalog/?chat=1");
    const mod = await import("./supportChatControl");
    mod.installSupportChatControl();
    expect(mod.getSupportChatState()).toEqual({
      visible: true,
      open: true,
      unread: 0,
    });
    expect(win.location.search).not.toContain("chat=");
  });

  it("applies ?chat=0 to hide the widget", async () => {
    installBrowserGlobals("/?chat=0");
    const mod = await import("./supportChatControl");
    mod.installSupportChatControl();
    expect(mod.getSupportChatState()).toEqual({
      visible: false,
      open: false,
      unread: 0,
    });
  });

  it("shares unread badge and clears it when the panel opens", async () => {
    installBrowserGlobals("/");
    const mod = await import("./supportChatControl");
    mod.installSupportChatControl();

    mod.setSupportChatUnread(3);
    expect(mod.getSupportChatState().unread).toBe(3);

    const seen: number[] = [];
    const unsubscribe = mod.subscribeSupportChat((s) => seen.push(s.unread));
    mod.setSupportChatUnread(5);
    expect(seen.at(-1)).toBe(5);
    unsubscribe();

    /* Opening the panel marks replies read — dock/FAB badge must clear. */
    mod.openSupportChat();
    expect(mod.getSupportChatState().unread).toBe(0);

    mod.setSupportChatUnread(Number.NaN);
    mod.setSupportChatUnread(-2);
    expect(mod.getSupportChatState().unread).toBe(0);
  });
});
