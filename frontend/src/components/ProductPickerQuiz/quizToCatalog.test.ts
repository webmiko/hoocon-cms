import { describe, expect, it } from "vitest";

import type { CatalogFacet } from "../../api/client";
import { QUIZ_CATEGORY } from "./quizCategories";
import { matchControlFacet } from "./quizFacetMatch";
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
    values: [
      { value: "25", count: 4 },
      { value: "65", count: 1 },
      { value: "150", count: 1 },
    ],
  },
  {
    key: "kvs",
    label: "Kvs",
    values: [
      { value: "1,6", count: 2 },
      { value: "10", count: 3 },
      { value: "16", count: 2 },
      { value: "40", count: 1 },
      { value: "63", count: 1 },
      { value: "100", count: 1 },
      { value: "400", count: 1 },
    ],
  },
  {
    key: "ways",
    label: "Тип крана",
    values: [
      { value: "2-ходовый", count: 5 },
      { value: "3-ходовый", count: 2 },
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
    // Fire/smoke: no control facet pin (discrete-only category).
    expect(fire.control).toBeUndefined();
  });

  it("maps kit control facet alongside voltage and aux", () => {
    const params = buildCatalogParams(
      {
        need: "kit",
        voltage: "24",
        control: "modulating",
        auxSwitch: "yes",
      },
      ACTUATOR_FACETS,
    );
    expect(params.category).toBe(QUIZ_CATEGORY.kit);
    expect(params.voltage).toBe("24 В AC/DC");
    expect(params.control).toBe("Пропорциональное 0…10 В");
    expect(params.aux_switch).toBe("SPDT-2");
  });

  it("maps kit answers to dn, kvs and ways facets", () => {
    const params = buildCatalogParams(
      {
        need: "kit",
        voltage: "24",
        control: "onoff",
        auxSwitch: "no",
        dn: "25",
        kvs: "6_to_16",
        ways: "3",
      },
      [...ACTUATOR_FACETS, ...BALL_VALVE_FACETS],
    );
    expect(params.category).toBe(QUIZ_CATEGORY.kit);
    expect(params.dn).toBe("25");
    expect(params.kvs).toBe("10,16");
    expect(params.ways).toBe("3-ходовый");
    expect(params.aux_switch).toBe("Нет");
  });

  it("maps smoke spring/no-spring to HVD vs SA search", () => {
    const spring = buildCatalogParams(
      {
        need: "actuator",
        application: "smoke",
        smokeReturn: "spring",
        control: "onoff",
        voltage: "skip",
        damperArea: "skip",
        damperType: "skip",
        damperPressure: "skip",
      },
      ACTUATOR_FACETS,
    );
    expect(spring.category).toBe(QUIZ_CATEGORY.smoke);
    expect(spring.q).toBe("HVD");
    expect(spring.control).toBeUndefined();

    const noSpring = buildCatalogParams(
      {
        need: "actuator",
        application: "smoke",
        smokeReturn: "no_spring",
        control: "onoff",
        tempSensor: "no",
        voltage: "skip",
        damperArea: "skip",
        damperType: "skip",
        damperPressure: "skip",
      },
      ACTUATOR_FACETS,
    );
    expect(noSpring.q).toBe("SA");
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
    expect(params.dn).toBe("25");
    expect(params.kvs).toBe("10,16");
    expect(params.ways).toBe("2-ходовый");
  });

  it("maps 8100Q DN65 and over-40 Kvs to flanged body facets", () => {
    const params = buildCatalogParams(
      {
        need: "ball_valve",
        dn: "65",
        kvs: "over_40",
        ways: "2",
      },
      BALL_VALVE_FACETS,
    );
    expect(params.category).toBe(QUIZ_CATEGORY.ballValve);
    expect(params.dn).toBe("65");
    expect(params.kvs).toBe("63,100,400");
    expect(params.ways).toBe("2-ходовый");
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

  it("relaxes only soft sizing/aux filters — keeps control and voltage", () => {
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
    expect(variants).toHaveLength(4);
    expect(variants[1]).not.toHaveProperty("area");
    expect(variants[2]).not.toHaveProperty("moment");
    expect(variants[3]).not.toHaveProperty("aux_switch");
    const last = variants[variants.length - 1]!;
    expect(last.control).toBe("Открыто/закрыто");
    expect(last.voltage).toBe("230 В");
    expect(last.temp_sensor).toBe("SAF72");
  });
});

describe("matchControlFacet", () => {
  it("treats 2-/3-position as discrete on/off intent", () => {
    expect(
      matchControlFacet(["2-/3-позиционное", "Пропорциональное"], "onoff"),
    ).toBe("2-/3-позиционное");
  });

  it("ORs both discrete chips so DA and HVD stay in on/off results", () => {
    expect(
      matchControlFacet(
        ["Открыто/закрыто", "2-/3-позиционное", "Пропорциональное"],
        "onoff",
      ),
    ).toBe("2-/3-позиционное,Открыто/закрыто");
  });

  it("maps modulating to proportional chip", () => {
    expect(
      matchControlFacet(
        ["Открыто/закрыто", "Пропорциональное 0…10 В"],
        "modulating",
      ),
    ).toBe("Пропорциональное 0…10 В");
  });
});
