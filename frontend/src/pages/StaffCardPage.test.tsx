import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StaffCardPage } from "./StaffCardPage";

let container: HTMLDivElement;
let root: Root;

function renderAt(path: string) {
  act(() => {
    root.render(
      <HelmetProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/komanda/:slug" element={<StaffCardPage />} />
          </Routes>
        </MemoryRouter>
      </HelmetProvider>,
    );
  });
}

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("StaffCardPage", () => {
  it("makes phone, mail and messengers actionable", () => {
    renderAt("/komanda/popova");
    const hrefs = Array.from(container.querySelectorAll("a")).map((link) =>
      link.getAttribute("href"),
    );
    expect(hrefs).toEqual([
      "tel:+79957807018",
      "tel:+78003505898",
      "mailto:assistant@hoocon.ru",
      "https://t.me/+79957807018",
      "https://wa.me/79957807018",
      "https://www.hoocon.ru",
    ]);
    expect(container.textContent).toContain("Людмила Попова");
    const given = container.querySelector("h1 span");
    expect(given?.textContent).toBe("Людмила");
    expect(container.querySelector("h1")?.textContent).toContain("Попова");
    expect(container.textContent).toContain("Бренд-менеджер");
    expect(container.textContent).toContain("+7 (995) 780-70-18");
    expect(container.querySelector("svg[aria-label='QR-код с контактом']")).not.toBeNull();
    expect(container.textContent).not.toContain("Каталог");
  });

  it("copies the WeChat id instead of opening a dead link", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    renderAt("/komanda/popova");
    const button = Array.from(container.querySelectorAll("button")).find((item) =>
      item.textContent?.includes("ludmilapopova"),
    );
    expect(button).toBeDefined();
    await act(async () => {
      button!.click();
    });
    expect(writeText).toHaveBeenCalledWith("ludmilapopova");
    expect(container.textContent).toContain("скопировано");
  });

  it("downloads the same contact the QR encodes", () => {
    const createObjectURL = vi.fn(() => "blob:card");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    renderAt("/komanda/popova");
    const button = Array.from(container.querySelectorAll("button")).find(
      (item) => item.textContent === "Сохранить контакт",
    );
    expect(button).toBeDefined();
    act(() => button!.click());
    const blob = createObjectURL.mock.calls[0]?.[0] as Blob;
    expect(blob.type).toContain("text/vcard");
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:card");
  });

  it("dials the UIS 499 number with Shevchenko's extension", () => {
    renderAt("/komanda/shevchenko");
    const hrefs = Array.from(container.querySelectorAll("a")).map((link) =>
      link.getAttribute("href"),
    );
    expect(hrefs).toEqual([
      "tel:+74999951277,202",
      "tel:+78003505898",
      "mailto:alexander@hoocon.ru",
      "https://www.hoocon.ru",
    ]);
    expect(container.querySelector("h1 span")?.textContent).toBe("Александр");
    expect(container.textContent).toContain("Шевченко");
    expect(container.textContent).toContain("+7 (499) 995-12-77 доб. 202");
    expect(container.textContent).toContain("8 800 350-58-98");
    expect(container.textContent).not.toContain("495");
    expect(container.textContent).not.toContain("Telegram");
    expect(container.textContent).not.toContain("WhatsApp");
    expect(container.textContent).not.toContain("WeChat");
  });

  it("does not show another person's number for an unknown slug", () => {
    renderAt("/komanda/net-takoy");
    expect(container.textContent).toContain("Такой визитки нет");
    expect(container.textContent).not.toContain("780-70-18");
    expect(container.textContent).not.toContain("assistant@hoocon.ru");
  });
});
