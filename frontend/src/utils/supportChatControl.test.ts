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
    expect(mod.getSupportChatState()).toEqual({ visible: true, open: false });

    (win.hooconChat as { open: () => void }).open();
    expect(mod.getSupportChatState()).toEqual({ visible: true, open: true });

    (win.hooconChat as { hide: () => void }).hide();
    expect(mod.getSupportChatState()).toEqual({ visible: false, open: false });
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
    expect(mod.getSupportChatState()).toEqual({ visible: true, open: true });
    expect(win.location.search).not.toContain("chat=");
  });

  it("applies ?chat=0 to hide the widget", async () => {
    installBrowserGlobals("/?chat=0");
    const mod = await import("./supportChatControl");
    mod.installSupportChatControl();
    expect(mod.getSupportChatState()).toEqual({ visible: false, open: false });
  });
});
