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

  it("locks 8100Q DN65–150 to 2-way and over-40 Kvs, skips sizing steps", () => {
    let state = applyQuizChoice(createInitialQuizState(), "ball_valve");
    state = applyQuizChoice(state, "65");
    expect(state.phase).toBe("results");
    expect(plannedQuizSteps(state.answers)).toEqual(["need", "dn"]);
    expect(state.answers).toMatchObject({
      need: "ball_valve",
      dn: "65",
      kvs: "over_40",
      ways: "2",
    });

    state = goBackQuizStep(state);
    expect(state.phase).toBe("questions");
    expect(getCurrentStepId(state)).toBe("dn");

    state = applyQuizChoice(state, "150");
    expect(state.phase).toBe("results");
    expect(state.answers.dn).toBe("150");
    expect(state.answers.ways).toBe("2");
    expect(state.answers.kvs).toBe("over_40");
  });

  it("clears flanged locks when DN goes back to brass path", () => {
    let state = applyQuizChoice(createInitialQuizState(), "ball_valve");
    state = applyQuizChoice(state, "80");
    expect(state.answers.ways).toBe("2");
    state = goBackQuizStep(state);
    state = goBackQuizStep(state);
    expect(state.answers.dn).toBeUndefined();
    expect(state.answers.kvs).toBeUndefined();
    expect(state.answers.ways).toBeUndefined();

    state = applyQuizChoice(state, "ball_valve");
    state = applyQuizChoice(state, "32");
    expect(getCurrentStepId(state)).toBe("kvs");
    expect(state.answers.ways).toBeUndefined();
    expect(state.answers.kvs).toBeUndefined();
    expect(plannedQuizSteps(state.answers)).toEqual([
      "need",
      "dn",
      "kvs",
      "ways",
    ]);
  });

  it("kit branch with flanged DN skips kvs/ways after voltage/control/aux", () => {
    let state = applyQuizChoice(createInitialQuizState(), "kit");
    state = applyQuizChoice(state, "24");
    state = applyQuizChoice(state, "onoff");
    state = applyQuizChoice(state, "yes");
    expect(getCurrentStepId(state)).toBe("dn");
    state = applyQuizChoice(state, "100");
    expect(state.phase).toBe("results");
    expect(plannedQuizSteps(state.answers)).toEqual([
      "need",
      "voltage",
      "control",
      "aux_switch",
      "dn",
    ]);
    expect(state.answers).toMatchObject({
      need: "kit",
      dn: "100",
      kvs: "over_40",
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

  it("keeps planned steps consistent with applyQuizChoice for every branch", () => {
    type Path = { label: string; choices: string[] };
    const paths: Path[] = [
      {
        label: "actuator/general",
        choices: [
          "actuator",
          "general",
          "230",
          "onoff",
          "no",
          "0_6_1_0",
          "rectangular",
          "medium",
        ],
      },
      {
        label: "actuator/failsafe/electronic",
        choices: [
          "actuator",
          "failsafe",
          "electronic",
          "24",
          "modulating",
          "yes",
          "1_0_1_6",
          "round",
          "low",
        ],
      },
      {
        label: "actuator/fire",
        choices: [
          "actuator",
          "fire",
          "230",
          "yes",
          "0_3_0_6",
          "rectangular",
          "high",
        ],
      },
      {
        label: "actuator/smoke/spring",
        choices: [
          "actuator",
          "smoke",
          "spring",
          "24",
          "no",
          "up_to_0_3",
          "gate",
          "very_high",
        ],
      },
      {
        label: "actuator/smoke/no_spring",
        choices: [
          "actuator",
          "smoke",
          "no_spring",
          "230",
          "0_6_1_0",
          "rectangular",
          "medium",
        ],
      },
      {
        label: "actuator/fast",
        choices: [
          "actuator",
          "fast",
          "24",
          "onoff",
          "skip",
          "2_5_4_0",
          "skip",
          "skip",
        ],
      },
      {
        label: "ball_valve/brass",
        choices: ["ball_valve", "40", "16_to_40", "3"],
      },
      {
        label: "ball_valve/8100Q",
        choices: ["ball_valve", "100"],
      },
      {
        label: "kit/brass",
        choices: ["kit", "230", "modulating", "no", "20", "2_5_to_6", "2"],
      },
      {
        label: "kit/flanged",
        choices: ["kit", "24", "onoff", "yes", "65"],
      },
      {
        label: "adapter",
        choices: ["adapter", "br_ml"],
      },
    ];

    for (const path of paths) {
      let state = createInitialQuizState();
      for (const choice of path.choices) {
        expect(state.phase, path.label).toBe("questions");
        const plan = plannedQuizSteps(state.answers);
        const current = getCurrentStepId(state);
        expect(plan, `${path.label} @ ${current}`).toContain(current);
        state = applyQuizChoice(state, choice);
      }
      expect(state.phase, path.label).toBe("results");
      const finalPlan = plannedQuizSteps(state.answers);
      for (const step of state.stepStack) {
        expect(finalPlan, `${path.label} stack`).toContain(step);
      }
    }
  });
});
