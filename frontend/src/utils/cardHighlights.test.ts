import { describe, expect, it } from "vitest";

import {
  CARD_HIGHLIGHT_MAX,
  cardHighlights,
  compactCardSpecName,
} from "./cardHighlights";

describe("cardHighlights", () => {
  it("keeps only the unified primary set (drops runtime/weight)", () => {
    const rows = [
      { key: "moment", name: "Крутящий момент", value: "3 Нм" },
      { key: "voltage", name: "Напряжение", value: "24 В" },
      { key: "control", name: "Управление", value: "Открыто/закрыто" },
      { key: "area", name: "Площадь", value: "до 0,3 м²" },
      { key: "aux_switch", name: "Вспомогательный переключатель", value: "SPDT-1" },
      { key: "runtime", name: "Время", value: "≤ 25 с" },
      { key: "weight", name: "Масса", value: "1 кг" },
      { key: "ip", name: "IP", value: "IP54" },
    ];
    expect(cardHighlights(rows).map((h) => h.key)).toEqual([
      "moment",
      "voltage",
      "control",
      "area",
      "aux_switch",
    ]);
  });

  it("keeps Y/U + aux for modulating editions under the cap", () => {
    const rows = [
      { key: "moment", name: "Крутящий момент", value: "5 Нм" },
      { key: "voltage", name: "Напряжение", value: "24 В" },
      { key: "control", name: "Управление", value: "Пропорциональное" },
      { key: "control_signal", name: "Y", value: "0…10 В" },
      { key: "feedback_signal", name: "U", value: "0…10 В" },
      { key: "area", name: "Площадь", value: "до 0,5 м²" },
      { key: "aux_switch", name: "Вспомогательный переключатель", value: "Нет" },
      { key: "runtime", name: "Время", value: "≤ 20 с" },
    ];
    const out = cardHighlights(rows, CARD_HIGHLIGHT_MAX);
    expect(out).toHaveLength(7);
    expect(out.map((h) => h.key)).toEqual([
      "moment",
      "voltage",
      "control",
      "control_signal",
      "feedback_signal",
      "area",
      "aux_switch",
    ]);
  });
});

describe("compactCardSpecName", () => {
  it("shortens Управляющий on Y-signal labels", () => {
    expect(compactCardSpecName("Управляющий сигнал Y")).toBe("Упр. сигнал Y");
    expect(compactCardSpecName("Упр. сигнал Y")).toBe("Упр. сигнал Y");
    expect(compactCardSpecName("Напряжение")).toBe("Напряжение");
    expect(compactCardSpecName("Обратная связь U")).toBe("Обратная связь U");
  });
});
