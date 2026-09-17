import { describe, expect, it } from "vitest";

import {
  buildQuizAnalogParams,
  shouldFetchKitAnalogs,
} from "./quizAnalogParams";

describe("quizAnalogParams", () => {
  it("builds kit analog API params from quiz answers and catalog facets", () => {
    const params = buildQuizAnalogParams(
      {
        need: "kit",
        voltage: "24",
        control: "onoff",
        auxSwitch: "no",
        dn: "25",
        kvs: "6_to_16",
        ways: "2",
      },
      {
        category: "komplekty",
        page: "1",
        page_size: "6",
        dn: "25",
        kvs: "10,16",
        ways: "2-ходовый",
      },
    );
    expect(params).toEqual({
      need: "kit",
      page_size: "6",
      quiz_voltage: "24",
      quiz_control: "onoff",
      quiz_aux: "no",
      dn: "25",
      kvs: "10,16",
      ways: "2-ходовый",
    });
  });

  it("requests kit analogs when factory kits are missing or out of stock", () => {
    expect(shouldFetchKitAnalogs("kit", [])).toBe(true);
    expect(
      shouldFetchKitAnalogs("kit", [{ in_stock: false }, { in_stock: false }]),
    ).toBe(true);
    expect(shouldFetchKitAnalogs("kit", [{ in_stock: true }])).toBe(false);
    expect(shouldFetchKitAnalogs("ball_valve", [{ in_stock: false }])).toBe(
      false,
    );
  });
});
