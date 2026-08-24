export type QuizNeed = "actuator" | "ball_valve" | "kit" | "adapter";

export type QuizApplication =
  | "general"
  | "fire"
  | "smoke"
  | "failsafe"
  | "fast";

export type QuizFailsafeType = "spring" | "electronic";

/** Smoke dampers: HVD-…F (spring) vs SA…MU (no spring). */
export type QuizSmokeReturn = "spring" | "no_spring" | "skip";

export type QuizVoltage = "24" | "230" | "skip";

export type QuizControl = "onoff" | "modulating" | "skip";

/** Damper passage area band (m²) — engineer-facing input. */
export type QuizDamperArea =
  | "up_to_0_3"
  | "0_3_0_6"
  | "0_6_1_0"
  | "1_0_1_6"
  | "1_6_2_5"
  | "2_5_4_0"
  | "over_4"
  | "skip";

/** Typical working pressure on the damper (Pa). */
export type QuizDamperPressure = "low" | "medium" | "high" | "very_high" | "skip";

/** Blade / frame type — Kтип in M = S × P × Kтип × Kзapас. */
export type QuizDamperType = "round" | "rectangular" | "gate" | "skip";

export type QuizDn =
  | "15"
  | "20"
  | "25"
  | "32"
  | "40"
  | "50"
  | "65"
  | "80"
  | "100"
  | "125"
  | "150"
  | "skip";

/** Flow coefficient band (m³/h) — maps to catalog Kvs facet. */
export type QuizKvs =
  | "up_to_2_5"
  | "2_5_to_6"
  | "6_to_16"
  | "16_to_40"
  | "over_40"
  | "skip";

export type QuizWays = "2" | "3" | "skip";

/** Hoocon ball-valve bracket: BR-M (MU/MQU) or BR-ML (FU). */
export type QuizAdapterType = "br_m" | "br_ml" | "skip";

/** Auxiliary SPDT switches for position feedback in BMS (DS/AS/S editions). */
export type QuizAuxSwitch = "yes" | "no" | "skip";

/** SAF72 thermal cut-out (~72 °C) — fire/smoke valve editions only. */
export type QuizTempSensor = "yes" | "no" | "skip";

export type QuizStepId =
  | "need"
  | "application"
  | "failsafe_type"
  | "smoke_return"
  | "voltage"
  | "control"
  | "aux_switch"
  | "temp_sensor"
  | "damper_area"
  | "damper_type"
  | "damper_pressure"
  | "dn"
  | "kvs"
  | "ways"
  | "adapter_type";

export type QuizAnswers = {
  need?: QuizNeed;
  application?: QuizApplication;
  failsafeType?: QuizFailsafeType;
  smokeReturn?: QuizSmokeReturn;
  voltage?: QuizVoltage;
  control?: QuizControl;
  damperArea?: QuizDamperArea;
  damperType?: QuizDamperType;
  damperPressure?: QuizDamperPressure;
  dn?: QuizDn;
  kvs?: QuizKvs;
  ways?: QuizWays;
  adapterType?: QuizAdapterType;
  auxSwitch?: QuizAuxSwitch;
  tempSensor?: QuizTempSensor;
};

export type QuizPhase = "questions" | "results";

export type QuizState = {
  answers: QuizAnswers;
  /** Stack of visited question steps; current step is the last entry. */
  stepStack: QuizStepId[];
  phase: QuizPhase;
};

export function createInitialQuizState(): QuizState {
  return {
    answers: {},
    stepStack: ["need"],
    phase: "questions",
  };
}

/** DN65–150 flanged 8100Q / H8103… bodies — 2-way only, one Kvs per DN. */
const FLANGED_8100Q_DNS = new Set<Exclude<QuizDn, "skip">>([
  "65",
  "80",
  "100",
  "125",
  "150",
]);

export function quizDnIsFlanged8100Q(dn: QuizDn | undefined): boolean {
  return dn != null && dn !== "skip" && FLANGED_8100Q_DNS.has(dn);
}

/**
 * Kvs / ways after DN — skipped for flanged 8100Q (fixed 2-way + Kvs > 40).
 * Brass DN15–50 and «не знаю» still ask both.
 */
export function quizNeedsBallValveSizingSteps(answers: QuizAnswers): boolean {
  if (answers.need !== "ball_valve" && answers.need !== "kit") {
    return false;
  }
  return !quizDnIsFlanged8100Q(answers.dn);
}

/** Fire always; smoke only when HVD-F (or unknown) — SA…MU has no SAF72 in catalog. */
export function quizNeedsTempSensorStep(answers: QuizAnswers): boolean {
  if (answers.need !== "actuator") {
    return false;
  }
  if (answers.application === "fire") {
    return true;
  }
  if (answers.application === "smoke") {
    return answers.smokeReturn !== "no_spring";
  }
  return false;
}

/**
 * Control type (on/off vs modulating) — skip for fire/smoke valves.
 * SAFU / SAMU are 2-/3-position only; no 0…10 V editions in catalog.
 */
export function quizNeedsControlStep(answers: QuizAnswers): boolean {
  if (answers.need !== "actuator") {
    return false;
  }
  if (answers.application === "fire" || answers.application === "smoke") {
    return false;
  }
  return true;
}

/** Optional aux on ventilation / fast / fail-safe actuators and H81 kits. */
export function quizNeedsAuxStep(answers: QuizAnswers): boolean {
  if (answers.need === "kit") {
    return true;
  }
  if (answers.need !== "actuator") {
    return false;
  }
  if (answers.application === "fire" || answers.application === "smoke") {
    return false;
  }
  return true;
}

/** After voltage (or control): temp sensor, aux, or damper sizing. */
function stepAfterVoltageOrControl(answers: QuizAnswers): QuizStepId {
  if (quizNeedsTempSensorStep(answers)) {
    return "temp_sensor";
  }
  if (quizNeedsAuxStep(answers)) {
    return "aux_switch";
  }
  return "damper_area";
}

function functionalStepsAfterControl(answers: QuizAnswers): QuizStepId[] {
  const steps: QuizStepId[] = [];
  if (quizNeedsTempSensorStep(answers)) {
    steps.push("temp_sensor");
  } else if (quizNeedsAuxStep(answers)) {
    steps.push("aux_switch");
  }
  return steps;
}

export function getCurrentStepId(state: QuizState): QuizStepId {
  return state.stepStack[state.stepStack.length - 1] ?? "need";
}

/** Ordered steps for the active branch (for progress rail). */
export function plannedQuizSteps(answers: QuizAnswers): QuizStepId[] {
  if (!answers.need) {
    return ["need"];
  }
  if (answers.need === "ball_valve") {
    if (quizNeedsBallValveSizingSteps(answers)) {
      return ["need", "dn", "kvs", "ways"];
    }
    return ["need", "dn"];
  }
  if (answers.need === "kit") {
    const steps: QuizStepId[] = [
      "need",
      "voltage",
      "control",
    ];
    if (quizNeedsAuxStep(answers)) {
      steps.push("aux_switch");
    }
    steps.push("dn");
    if (quizNeedsBallValveSizingSteps(answers)) {
      steps.push("kvs", "ways");
    }
    return steps;
  }
  if (answers.need === "adapter") {
    return ["need", "adapter_type"];
  }
  const steps: QuizStepId[] = ["need", "application"];
  if (answers.application === "failsafe") {
    steps.push("failsafe_type");
  }
  if (answers.application === "smoke") {
    steps.push("smoke_return");
  }
  steps.push("voltage");
  if (quizNeedsControlStep(answers)) {
    steps.push("control");
  }
  steps.push(...functionalStepsAfterControl(answers));
  steps.push("damper_area", "damper_type", "damper_pressure");
  return steps;
}

export function quizProgressIndex(state: QuizState): {
  current: number;
  total: number;
} {
  const plan = plannedQuizSteps(state.answers);
  const currentStep = getCurrentStepId(state);
  const idx = plan.indexOf(currentStep);
  return {
    current: idx >= 0 ? idx + 1 : state.stepStack.length,
    total: plan.length,
  };
}

function setAnswerForStep(
  answers: QuizAnswers,
  stepId: QuizStepId,
  choiceId: string,
): QuizAnswers {
  const next = { ...answers };
  switch (stepId) {
    case "need":
      next.need = choiceId as QuizNeed;
      break;
    case "application":
      next.application = choiceId as QuizApplication;
      break;
    case "failsafe_type":
      next.failsafeType = choiceId as QuizFailsafeType;
      break;
    case "smoke_return":
      next.smokeReturn = choiceId as QuizSmokeReturn;
      break;
    case "voltage":
      next.voltage = choiceId as QuizVoltage;
      break;
    case "control":
      next.control = choiceId as QuizControl;
      break;
    case "damper_area":
      next.damperArea = choiceId as QuizDamperArea;
      break;
    case "damper_type":
      next.damperType = choiceId as QuizDamperType;
      break;
    case "damper_pressure":
      next.damperPressure = choiceId as QuizDamperPressure;
      break;
    case "dn":
      next.dn = choiceId as QuizDn;
      break;
    case "kvs":
      next.kvs = choiceId as QuizKvs;
      break;
    case "ways":
      next.ways = choiceId as QuizWays;
      break;
    case "adapter_type":
      next.adapterType = choiceId as QuizAdapterType;
      break;
    case "aux_switch":
      next.auxSwitch = choiceId as QuizAuxSwitch;
      break;
    case "temp_sensor":
      next.tempSensor = choiceId as QuizTempSensor;
      break;
    default:
      break;
  }
  return next;
}

function nextStepAfter(
  answers: QuizAnswers,
  currentStep: QuizStepId,
): QuizStepId | "results" {
  switch (currentStep) {
    case "need":
      if (answers.need === "actuator") return "application";
      if (answers.need === "ball_valve") return "dn";
      if (answers.need === "kit") return "voltage";
      if (answers.need === "adapter") return "adapter_type";
      return "results";
    case "application":
      if (answers.application === "failsafe") return "failsafe_type";
      if (answers.application === "smoke") return "smoke_return";
      return "voltage";
    case "failsafe_type":
      return "voltage";
    case "smoke_return":
      return "voltage";
    case "voltage":
      if (answers.need === "kit") {
        return "control";
      }
      if (answers.need === "actuator") {
        return quizNeedsControlStep(answers)
          ? "control"
          : stepAfterVoltageOrControl(answers);
      }
      return "results";
    case "control":
      if (answers.need === "kit") {
        if (quizNeedsAuxStep(answers)) {
          return "aux_switch";
        }
        return "dn";
      }
      return stepAfterVoltageOrControl(answers);
    case "temp_sensor":
      return "damper_area";
    case "aux_switch":
      if (answers.need === "kit") {
        return "dn";
      }
      return "damper_area";
    case "damper_area":
      return "damper_type";
    case "damper_type":
      return "damper_pressure";
    case "damper_pressure":
    case "ways":
    case "adapter_type":
      return "results";
    case "dn":
      if (quizDnIsFlanged8100Q(answers.dn)) {
        return "results";
      }
      return "kvs";
    case "kvs":
      return "ways";
    default:
      return "results";
  }
}

export function applyQuizChoice(
  state: QuizState,
  choiceId: string,
): QuizState {
  const stepId = getCurrentStepId(state);
  let answers = setAnswerForStep(state.answers, stepId, choiceId);
  if (stepId === "need") {
    answers = { need: answers.need };
  } else if (stepId === "application") {
    answers = {
      need: answers.need,
      application: answers.application,
    };
  }
  // Fire/smoke: only on/off in catalog — lock control without asking.
  if (
    stepId === "application" &&
    (answers.application === "fire" || answers.application === "smoke")
  ) {
    answers = { ...answers, control: "onoff" };
  }
  // SA…MU: no published DST — skip temp filter entirely.
  if (stepId === "smoke_return" && answers.smokeReturn === "no_spring") {
    answers = { ...answers, tempSensor: "no" };
  }
  // 8100Q / flanged kits: only 2-way, Kvs always > 40 — lock and skip steps.
  if (stepId === "dn") {
    if (quizDnIsFlanged8100Q(answers.dn)) {
      answers = { ...answers, ways: "2", kvs: "over_40" };
    } else {
      const cleared = { ...answers };
      delete cleared.ways;
      delete cleared.kvs;
      answers = cleared;
    }
  }
  const next = nextStepAfter(answers, stepId);
  if (next === "results") {
    return {
      answers,
      stepStack: state.stepStack,
      phase: "results",
    };
  }
  return {
    answers,
    stepStack: [...state.stepStack, next],
    phase: "questions",
  };
}

export function skipQuizStep(state: QuizState): QuizState {
  const stepId = getCurrentStepId(state);
  // DN skip must clear flanged auto-locks the same way as applyQuizChoice.
  if (stepId === "dn") {
    return applyQuizChoice(state, "skip");
  }
  const copy = QUIZ_SKIP_FIELD[stepId];
  if (!copy) {
    return applyQuizChoice(state, "skip");
  }
  const answers = { ...state.answers, [copy]: "skip" as never };
  const next = nextStepAfter(answers, stepId);
  if (next === "results") {
    return { answers, stepStack: state.stepStack, phase: "results" };
  }
  return {
    answers,
    stepStack: [...state.stepStack, next],
    phase: "questions",
  };
}

const QUIZ_SKIP_FIELD: Partial<Record<QuizStepId, keyof QuizAnswers>> = {
  voltage: "voltage",
  control: "control",
  aux_switch: "auxSwitch",
  temp_sensor: "tempSensor",
  smoke_return: "smokeReturn",
  damper_area: "damperArea",
  damper_type: "damperType",
  damper_pressure: "damperPressure",
  dn: "dn",
  kvs: "kvs",
  ways: "ways",
  adapter_type: "adapterType",
};

const STEP_ANSWER_KEY: Partial<Record<QuizStepId, keyof QuizAnswers>> = {
  need: "need",
  application: "application",
  failsafe_type: "failsafeType",
  smoke_return: "smokeReturn",
  voltage: "voltage",
  control: "control",
  damper_area: "damperArea",
  damper_type: "damperType",
  damper_pressure: "damperPressure",
  dn: "dn",
  kvs: "kvs",
  ways: "ways",
  adapter_type: "adapterType",
  aux_switch: "auxSwitch",
  temp_sensor: "tempSensor",
};

export function goBackQuizStep(state: QuizState): QuizState {
  if (state.phase === "results") {
    return { ...state, phase: "questions" };
  }
  if (state.stepStack.length <= 1) {
    return state;
  }
  const dropped = state.stepStack[state.stepStack.length - 1];
  const stepStack = state.stepStack.slice(0, -1);
  const answers = { ...state.answers };
  const field = STEP_ANSWER_KEY[dropped];
  if (field) {
    delete answers[field];
  }
  if (dropped === "application") {
    delete answers.failsafeType;
    delete answers.smokeReturn;
    delete answers.auxSwitch;
    delete answers.tempSensor;
    delete answers.control;
  }
  // Flanged DN auto-locks ways/kvs without putting them on the stack.
  if (dropped === "dn") {
    delete answers.kvs;
    delete answers.ways;
  }
  return { answers, stepStack, phase: "questions" };
}

export function resetQuizState(): QuizState {
  return createInitialQuizState();
}

export function isQuizStarted(state: QuizState): boolean {
  return state.stepStack.length > 1 || state.phase === "results";
}
