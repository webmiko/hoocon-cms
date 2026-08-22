import { describe, expect, it } from "vitest";

import type { CatalogFacet } from "../../api/client";
import { QUIZ_CATEGORY } from "./quizCategories";
import {
  buildCatalogParams,
  catalogUrlFromParams,
  relaxCatalogParams,
  resolveQuizCategory,
} from "./quizToCatalog";

const ACTUATOR_FACETS: CatalogFacet[] = [
  {
    key: "voltage",
    label: "Напряжение",
    values: [{ value: "24 В AC/DC", count: 10 }, { value: "230 В", count: 8 }],
  },
  {
    key: "control",
    label: "Управление",
    values: [
      { value: "Открыто/закрыто", count: 12 },
      { value: "Пропорциональное 0…10 В", count: 6 },
    ],
  },
  {
    key: "aux_switch",
    label: "Вспомогательный переключатель",
    values: [
      { value: "Нет", count: 8 },
      { value: "SPDT-1", count: 2 },
      { value: "SPDT-2", count: 6 },
    ],
  },
  {
    key: "temp_sensor",
    label: "Термодатчик",
    values: [
      { value: "Нет", count: 5 },
      { value: "SAF72", count: 3 },
    ],
  },
  {
    key: "moment",
    label: "Крутящий момент",
    values: [
      { value: "5 Нм", count: 4 },
      { value: "10 Нм", count: 7 },
      { value: "20 Нм", count: 3 },
    ],
  },
  {
    key: "area",
    label: "Площадь заслонки",
    values: [
      { value: "до 0,5 м²", count: 4 },
      { value: "до 1,0 м²", count: 7 },
      { value: "до 2,0 м²", count: 3 },
    ],
  },
];

const BALL_VALVE_FACETS: CatalogFacet[] = [
  {
    key: "dn",
    label: "DN",
    values: [{ value: "DN 25", count: 4 }],
  },
  {
    key: "kvs",
    label: "Kvs",
    values: [
      { value: "1,6", count: 2 },
      { value: "10", count: 3 },
      { value: "16", count: 2 },
      { value: "40", count: 1 },
    ],
  },
  {
    key: "ways",
    label: "Тип крана",
    values: [
      { value: "2-ходовой", count: 5 },
      { value: "3-ходовой", count: 2 },
    ],
  },
];

describe("quizToCatalog", () => {
  it("maps actuator answers to category and derived moment/area facets", () => {
    const params = buildCatalogParams(
      {
        need: "actuator",
        application: "general",
        voltage: "230",
        control: "onoff",
        damperArea: "0_6_1_0",
        damperType: "rectangular",
        damperPressure: "medium",
      },
      ACTUATOR_FACETS,
    );
    expect(params.category).toBe(QUIZ_CATEGORY.general);
    expect(params.voltage).toBe("230 В");
    expect(params.control).toBe("Открыто/закрыто");
    expect(params.moment).toBe("10 Нм");
    expect(params.area).toBe("до 1,0 м²");
    expect(params.page_size).toBe("6");
  });

  it("maps aux and temp sensor facets for actuator answers", () => {
    const ventilation = buildCatalogParams(
      {
        need: "actuator",
        application: "general",
        voltage: "24",
        control: "modulating",
        auxSwitch: "yes",
        damperArea: "skip",
        damperType: "skip",
        damperPressure: "skip",
      },
      ACTUATOR_FACETS,
    );
    expect(ventilation.aux_switch).toBe("SPDT-2");

    const fire = buildCatalogParams(
      {
        need: "actuator",
        application: "fire",
        voltage: "24",
        control: "onoff",
        tempSensor: "yes",
        damperArea: "skip",
        damperType: "skip",
        damperPressure: "skip",
      },
      ACTUATOR_FACETS,
    );
    expect(fire.category).toBe(QUIZ_CATEGORY.fire);
    expect(fire.temp_sensor).toBe("SAF72");
    expect(fire.aux_switch).toBeUndefined();
  });

  it("maps fire application to SA category", () => {
    expect(
      resolveQuizCategory({
        need: "actuator",
        application: "fire",
      }),
    ).toBe(QUIZ_CATEGORY.fire);
  });

  it("builds catalog URL with facet query string", () => {
    const url = catalogUrlFromParams({
      category: QUIZ_CATEGORY.ballValve,
      page: "1",
      page_size: "6",
      dn: "DN 25",
    });
    expect(url).toBe("/catalog/sharovye-krany?dn=DN+25");
  });

  it("maps ball valve answers to dn, kvs and ways facets", () => {
    const params = buildCatalogParams(
      {
        need: "ball_valve",
        dn: "25",
        kvs: "6_to_16",
        ways: "2",
      },
      BALL_VALVE_FACETS,
    );
    expect(params.category).toBe(QUIZ_CATEGORY.ballValve);
    expect(params.dn).toBe("DN 25");
    expect(params.kvs).toBe("10");
    expect(params.ways).toBe("2-ходовой");
  });

  it("maps adapter type to exact catalog search by SKU code", () => {
    const brM = buildCatalogParams(
      {
        need: "adapter",
        adapterType: "br_m",
      },
      [],
    );
    expect(brM.category).toBe(QUIZ_CATEGORY.adapter);
    expect(brM.q).toBe("BR-M");

    const brMl = buildCatalogParams(
      {
        need: "adapter",
        adapterType: "br_ml",
      },
      [],
    );
    expect(brMl.category).toBe(QUIZ_CATEGORY.adapter);
    expect(brMl.q).toBe("BR-ML");
  });

  it("relaxes ball valve filters in ways → kvs → dn order", () => {
    const strict = {
      category: QUIZ_CATEGORY.ballValve,
      page: "1",
      page_size: "6",
      dn: "DN 25",
      kvs: "10",
      ways: "2-ходовой",
    };
    const variants = relaxCatalogParams(strict);
    expect(variants).toHaveLength(4);
    expect(variants[1]).not.toHaveProperty("ways");
    expect(variants[2]).not.toHaveProperty("kvs");
    expect(variants[3]).not.toHaveProperty("dn");
  });

  it("relaxes filters in area → moment → temp → aux → control → voltage order", () => {
    const strict = {
      category: QUIZ_CATEGORY.general,
      page: "1",
      page_size: "6",
      area: "до 1,0 м²",
      moment: "10 Нм",
      temp_sensor: "SAF72",
      aux_switch: "SPDT-2",
      control: "Открыто/закрыто",
      voltage: "230 В",
    };
    const variants = relaxCatalogParams(strict);
    expect(variants).toHaveLength(7);
    expect(variants[1]).not.toHaveProperty("area");
    expect(variants[2]).not.toHaveProperty("moment");
    expect(variants[3]).not.toHaveProperty("temp_sensor");
    expect(variants[4]).not.toHaveProperty("aux_switch");
    expect(variants[5]).not.toHaveProperty("control");
    expect(variants[6]).not.toHaveProperty("voltage");
  });
});
