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
    expect(getCurrentStepId(state)).toBe("aux_switch");

    state = applyQuizChoice(state, "no");
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
      auxSwitch: "no",
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
      "aux_switch",
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

  it("skips control and inserts temp sensor for fire application", () => {
    let state = applyQuizChoice(createInitialQuizState(), "actuator");
    state = applyQuizChoice(state, "fire");
    expect(state.answers.control).toBe("onoff");
    expect(plannedQuizSteps(state.answers)).not.toContain("control");
    expect(plannedQuizSteps(state.answers)).toContain("temp_sensor");
    expect(plannedQuizSteps(state.answers)).not.toContain("aux_switch");

    state = applyQuizChoice(state, "24");
    expect(getCurrentStepId(state)).toBe("temp_sensor");

    state = applyQuizChoice(state, "yes");
    expect(getCurrentStepId(state)).toBe("damper_area");
    expect(state.answers.tempSensor).toBe("yes");
  });

  it("skips modulating control for smoke extraction", () => {
    let state = applyQuizChoice(createInitialQuizState(), "actuator");
    state = applyQuizChoice(state, "smoke");
    expect(state.answers.control).toBe("onoff");
    expect(getCurrentStepId(state)).toBe("smoke_return");
    expect(plannedQuizSteps(state.answers)).toContain("smoke_return");
    expect(plannedQuizSteps(state.answers)).not.toContain("control");

    state = applyQuizChoice(state, "spring");
    expect(getCurrentStepId(state)).toBe("voltage");
    expect(state.answers.smokeReturn).toBe("spring");

    state = applyQuizChoice(state, "230");
    expect(getCurrentStepId(state)).toBe("temp_sensor");
  });

  it("skips temp sensor for smoke without spring (SA…MU)", () => {
    let state = applyQuizChoice(createInitialQuizState(), "actuator");
    state = applyQuizChoice(state, "smoke");
    state = applyQuizChoice(state, "no_spring");
    expect(state.answers.tempSensor).toBe("no");
    expect(plannedQuizSteps(state.answers)).not.toContain("temp_sensor");

    state = applyQuizChoice(state, "24");
    expect(getCurrentStepId(state)).toBe("damper_area");
  });

  it("kit branch asks control, aux, then dn/kvs/ways after voltage", () => {
    let state = applyQuizChoice(createInitialQuizState(), "kit");
    expect(plannedQuizSteps(state.answers)).toEqual([
      "need",
      "voltage",
      "control",
      "aux_switch",
      "dn",
      "kvs",
      "ways",
    ]);
    state = applyQuizChoice(state, "24");
    expect(getCurrentStepId(state)).toBe("control");
    state = applyQuizChoice(state, "onoff");
    expect(getCurrentStepId(state)).toBe("aux_switch");
    state = applyQuizChoice(state, "yes");
    expect(getCurrentStepId(state)).toBe("dn");
    state = applyQuizChoice(state, "25");
    expect(getCurrentStepId(state)).toBe("kvs");
    state = applyQuizChoice(state, "6_to_16");
    expect(getCurrentStepId(state)).toBe("ways");
    state = applyQuizChoice(state, "2");
    expect(state.phase).toBe("results");
    expect(state.answers).toMatchObject({
      need: "kit",
      voltage: "24",
      control: "onoff",
      auxSwitch: "yes",
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
    state = applyQuizChoice(state, "24");
    state = applyQuizChoice(state, "onoff");
    state = skipQuizStep(state);
    expect(getCurrentStepId(state)).toBe("dn");
    expect(state.answers.auxSwitch).toBe("skip");
    state = skipQuizStep(state);
    state = skipQuizStep(state);
    state = skipQuizStep(state);
    expect(state.phase).toBe("results");
    expect(state.answers).toMatchObject({
      dn: "skip",
      kvs: "skip",
      ways: "skip",
    });
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
