import { describe, expect, it } from "vitest";

import {
  ceilToMomentLadder,
  estimateRequiredMomentNm,
} from "./quizMomentEstimate";

describe("quizMomentEstimate", () => {
  it("matches article example: 0,96 m² at 450 Pa rectangular → 10 Nm", () => {
    const required =
      (0.96 * 450 * 1.4 * 1.3) / 100;
    expect(required).toBeCloseTo(7.86, 2);
    expect(ceilToMomentLadder(required)).toBe(10);
  });

  it("derives moment from quiz answers (area + pressure + type)", () => {
    expect(
      estimateRequiredMomentNm({
        need: "actuator",
        damperArea: "0_6_1_0",
        damperPressure: "medium",
        damperType: "rectangular",
      }),
    ).toBe(10);
  });

  it("uses conservative defaults when pressure or type skipped", () => {
    expect(
      estimateRequiredMomentNm({
        need: "actuator",
        damperArea: "up_to_0_3",
      }),
    ).toBe(4);
  });

  it("steps up for gate dampers and high pressure", () => {
    expect(
      estimateRequiredMomentNm({
        need: "actuator",
        damperArea: "0_6_1_0",
        damperPressure: "very_high",
        damperType: "gate",
      }),
    ).toBe(40);
  });
});
