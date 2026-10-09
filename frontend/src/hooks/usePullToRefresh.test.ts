import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { pullGestureBlocked } from "./usePullToRefresh";

let host: HTMLDivElement;

beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
});

afterEach(() => {
  host.remove();
  document.body.style.overflow = "";
  document.documentElement.style.overflow = "";
});

describe("pullGestureBlocked", () => {
  it("allows the gesture on plain page content", () => {
    host.innerHTML = "<main><p id='t'>Каталог</p></main>";
    expect(pullGestureBlocked(host.querySelector("#t"))).toBe(false);
  });

  it("ignores touches inside the menu, lightbox and chat dialogs", () => {
    host.innerHTML = `
      <div role="dialog" aria-label="Меню сайта"><a id="menu">Каталог</a></div>
      <div role="dialog" aria-modal="true"><img id="lightbox" /></div>
      <dialog open><input id="native" /></dialog>`;
    for (const id of ["menu", "lightbox", "native"]) {
      expect(pullGestureBlocked(host.querySelector(`#${id}`))).toBe(true);
    }
  });

  it("leaves an inner scroll area to scroll itself", () => {
    host.innerHTML = "<div id='box' style='overflow-y:auto'><p id='t'>x</p></div>";
    const box = host.querySelector<HTMLDivElement>("#box")!;
    Object.defineProperty(box, "scrollHeight", { configurable: true, value: 800 });
    Object.defineProperty(box, "clientHeight", { configurable: true, value: 300 });
    expect(pullGestureBlocked(host.querySelector("#t"))).toBe(true);
  });

  it("is off while an overlay locks page scroll", () => {
    host.innerHTML = "<p id='t'>x</p>";
    document.body.style.overflow = "hidden";
    expect(pullGestureBlocked(host.querySelector("#t"))).toBe(true);
  });
});
