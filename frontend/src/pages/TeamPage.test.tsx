import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { StaffCardPage } from "./StaffCardPage";
import { TeamPage } from "./TeamPage";

let container: HTMLDivElement;
let root: Root;

function renderTeam() {
  act(() => {
    root.render(
      <HelmetProvider>
        <MemoryRouter initialEntries={["/komanda"]}>
          <Routes>
            <Route path="/komanda" element={<TeamPage />} />
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
});

describe("TeamPage", () => {
  it("presents each person with the UIS 499 line and a card link", () => {
    renderTeam();
    expect(container.querySelector("h1")?.textContent).toBe("Команда");
    expect(container.textContent).toContain("Прямые контакты сотрудников");
    expect(container.textContent).toContain("Бренд-менеджер");
    expect(container.textContent).toContain("Менеджер по продажам");
    expect(container.textContent).toContain("Менеджер отдела региональных продаж");
    expect(container.textContent).toContain("+7 (499) 995-12-77 доб. 202");
    expect(container.textContent).toContain("+7 (499) 995-12-77 доб. 203");
    expect(container.textContent).toContain("alexander@hoocon.ru");
    expect(container.textContent).toContain("larisa@hoocon.ru");
    expect(container.textContent).toContain("8 800 350-58-98");
    expect(container.textContent).not.toContain("495");

    const cardLinks = Array.from(container.querySelectorAll('a[href^="/komanda/"]')).map((link) =>
      link.getAttribute("href"),
    );
    expect(cardLinks).toEqual(["/komanda/popova", "/komanda/shevchenko", "/komanda/shinkarenko"]);

    const shevchenko = container.querySelector(
      'a[href="/komanda/shevchenko"]',
    ) as HTMLAnchorElement;
    expect(shevchenko.textContent).toBe("Визитка");
    act(() => {
      shevchenko.click();
    });
    expect(container.querySelector("h1")?.textContent).toContain("Шевченко");
    expect(container.textContent).toContain("Сохранить контакт");
  });
});
