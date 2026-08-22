import { describe, expect, it } from "vitest";

import {
  applyQuizChoice,
  createInitialQuizState,
  getCurrentStepId,
  goBackQuizStep,
  plannedQuizSteps,
  skipQuizStep,
} from "./quizEngine";

describe("quizEngine", () => {
  it("walks actuator branch through results", () => {
    let state = createInitialQuizState();
    state = applyQuizChoice(state, "actuator");
    expect(getCurrentStepId(state)).toBe("application");

    state = applyQuizChoice(state, "general");
    expect(getCurrentStepId(state)).toBe("voltage");

    state = applyQuizChoice(state, "230");
    expect(getCurrentStepId(state)).toBe("control");

    state = applyQuizChoice(state, "onoff");
    expect(getCurrentStepId(state)).toBe("damper_area");

    state = applyQuizChoice(state, "0_6_1_0");
    expect(getCurrentStepId(state)).toBe("damper_type");

    state = applyQuizChoice(state, "rectangular");
    expect(getCurrentStepId(state)).toBe("damper_pressure");

    state = applyQuizChoice(state, "medium");
    expect(state.phase).toBe("results");
    expect(state.answers).toMatchObject({
      need: "actuator",
      application: "general",
      voltage: "230",
      control: "onoff",
      damperArea: "0_6_1_0",
      damperType: "rectangular",
      damperPressure: "medium",
    });
  });

  it("inserts failsafe sub-step for spring return", () => {
    let state = applyQuizChoice(createInitialQuizState(), "actuator");
    state = applyQuizChoice(state, "failsafe");
    expect(getCurrentStepId(state)).toBe("failsafe_type");
    expect(plannedQuizSteps(state.answers)).toEqual([
      "need",
      "application",
      "failsafe_type",
      "voltage",
      "control",
      "damper_area",
      "damper_type",
      "damper_pressure",
    ]);

    state = applyQuizChoice(state, "spring");
    expect(getCurrentStepId(state)).toBe("voltage");
  });

  it("walks ball valve branch through dn, kvs and ways", () => {
    let state = applyQuizChoice(createInitialQuizState(), "ball_valve");
    expect(getCurrentStepId(state)).toBe("dn");
    expect(plannedQuizSteps(state.answers)).toEqual([
      "need",
      "dn",
      "kvs",
      "ways",
    ]);

    state = applyQuizChoice(state, "25");
    expect(getCurrentStepId(state)).toBe("kvs");

    state = applyQuizChoice(state, "6_to_16");
    expect(getCurrentStepId(state)).toBe("ways");

    state = applyQuizChoice(state, "2");
    expect(state.phase).toBe("results");
    expect(state.answers).toMatchObject({
      need: "ball_valve",
      dn: "25",
      kvs: "6_to_16",
      ways: "2",
    });
  });

  it("resets branch answers when need changes", () => {
    let state = applyQuizChoice(createInitialQuizState(), "actuator");
    state = applyQuizChoice(state, "general");
    state = goBackQuizStep(state);
    state = goBackQuizStep(state);
    state = applyQuizChoice(state, "kit");
    expect(state.answers).toEqual({ need: "kit" });
    expect(getCurrentStepId(state)).toBe("voltage");
  });

  it("skip sets optional facet to skip and advances", () => {
    let state = applyQuizChoice(createInitialQuizState(), "kit");
    state = skipQuizStep(state);
    expect(state.phase).toBe("results");
    expect(state.answers.voltage).toBe("skip");
  });

  it("walks adapter branch to BR-M or BR-ML", () => {
    let state = applyQuizChoice(createInitialQuizState(), "adapter");
    expect(getCurrentStepId(state)).toBe("adapter_type");
    expect(plannedQuizSteps(state.answers)).toEqual(["need", "adapter_type"]);

    state = applyQuizChoice(state, "br_m");
    expect(state.phase).toBe("results");
    expect(state.answers.adapterType).toBe("br_m");
  });
});
