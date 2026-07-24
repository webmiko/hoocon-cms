import { describe, expect, it } from "vitest";

import { facetLabelShort, facetValueShort } from "./facetDisplay";

describe("facetDisplay", () => {
  it("shortens voltage for narrow filter UI", () => {
    expect(facetValueShort("voltage", "AC/DC 24 В, 50/60 Гц")).toBe("24 В AC/DC");
    expect(facetValueShort("voltage", "AC 100…240 В, 50/60 Гц")).toBe("100…240 В");
  });

  it("shortens control and facet labels", () => {
    expect(facetValueShort("control", "Пропорциональное (модулирующее)")).toBe(
      "Пропорциональное",
    );
    expect(facetValueShort("control", "Открыто/закрыто")).toBe("Открыто/закрыто");
    expect(facetLabelShort("aux_switch", "Вспомогательный переключатель")).toBe(
      "Вспом. перекл.",
    );
    expect(facetLabelShort("temp_sensor", "Термодатчик")).toBe("Термодатчик");
    expect(facetLabelShort("analog", "Аналоги")).toBe("Аналоги");
    expect(facetLabelShort("material", "Материал корпуса")).toBe("Материал корпуса");
  });

  it("normalizes area to always «до N м²»", () => {
    expect(facetValueShort("area", "до 0,5")).toBe("до 0,5 м²");
    expect(facetValueShort("area", "3, 2 м²")).toBe("до 3,2 м²");
    expect(facetValueShort("area", "0,5 м²")).toBe("до 0,5 м²");
    expect(facetValueShort("area", "до 1")).toBe("до 1,0 м²");
    expect(facetValueShort("area", "до 1,0")).toBe("до 1,0 м²");
    expect(facetValueShort("area", "< 0,5 м²")).toBe("до 0,5 м²");
    expect(facetValueShort("area", "до < 0,5 м²")).toBe("до 0,5 м²");
  });
});
