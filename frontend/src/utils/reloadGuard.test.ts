import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createReloadGuard, RELOAD_RETRY_MS } from "./reloadGuard";

const here = dirname(fileURLToPath(import.meta.url));
const mainTsx = readFileSync(join(here, "..", "main.tsx"), "utf8");

function typeInto(el: HTMLInputElement | HTMLTextAreaElement, value: string) {
  el.value = value;
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

let host: HTMLDivElement;

beforeEach(() => {
  vi.useFakeTimers();
  host = document.createElement("div");
  document.body.appendChild(host);
});

afterEach(() => {
  host.remove();
  vi.useRealTimers();
});

describe("reloadGuard wiring in main.tsx", () => {
  it("routes both SW autoUpdate and the release check through the guard", () => {
    expect(mainTsx).toMatch(/onNeedReload\(\)\s*\{\s*guard\.requestReload\(\);/);
    expect(mainTsx).toContain("reloadIfReleaseStale(undefined, () => guard.requestReload())");
  });
});

describe("reloadGuard", () => {
  it("reloads immediately when nothing was typed (prefilled fields are fine)", () => {
    host.innerHTML = '<textarea id="m">Прошу подготовить КП на DA24.</textarea>';
    const reload = vi.fn();
    createReloadGuard().requestReload(reload);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("defers a deploy reload while an RFQ message is half-typed", () => {
    host.innerHTML = '<textarea id="m"></textarea>';
    const guard = createReloadGuard();
    typeInto(host.querySelector("textarea")!, "Нужно 40 шт.");

    const reload = vi.fn();
    guard.requestReload(reload);
    vi.advanceTimersByTime(RELOAD_RETRY_MS * 3);
    expect(reload).not.toHaveBeenCalled();

    typeInto(host.querySelector("textarea")!, "");
    vi.advanceTimersByTime(RELOAD_RETRY_MS);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("reloads once the form unmounts after navigation", () => {
    host.innerHTML = '<input type="email" />';
    const guard = createReloadGuard();
    typeInto(host.querySelector("input")!, "a@b.ru");
    const reload = vi.fn();
    guard.requestReload(reload);
    host.innerHTML = "";
    vi.advanceTimersByTime(RELOAD_RETRY_MS);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("ignores search boxes and collapses SW + health requests into one reload", () => {
    host.innerHTML = '<input type="search" />';
    const guard = createReloadGuard();
    typeInto(host.querySelector("input")!, "DA24");
    const reload = vi.fn();
    guard.requestReload(reload);
    guard.requestReload(reload);
    expect(reload).toHaveBeenCalledTimes(1);
  });
});
