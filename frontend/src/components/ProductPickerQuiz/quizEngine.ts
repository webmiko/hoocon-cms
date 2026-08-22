export type QuizNeed = "actuator" | "ball_valve" | "kit" | "adapter";

export type QuizApplication =
  | "general"
  | "fire"
  | "smoke"
  | "failsafe"
  | "fast";

export type QuizFailsafeType = "spring" | "electronic";

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

export type QuizDn = "15" | "20" | "25" | "32" | "40" | "50" | "skip";

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

export type QuizStepId =
  | "need"
  | "application"
  | "failsafe_type"
  | "voltage"
  | "control"
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
  voltage?: QuizVoltage;
  control?: QuizControl;
  damperArea?: QuizDamperArea;
  damperType?: QuizDamperType;
  damperPressure?: QuizDamperPressure;
  dn?: QuizDn;
  kvs?: QuizKvs;
  ways?: QuizWays;
  adapterType?: QuizAdapterType;
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

export function getCurrentStepId(state: QuizState): QuizStepId {
  return state.stepStack[state.stepStack.length - 1] ?? "need";
}

/** Ordered steps for the active branch (for progress rail). */
export function plannedQuizSteps(answers: QuizAnswers): QuizStepId[] {
  if (!answers.need) {
    return ["need"];
  }
  if (answers.need === "ball_valve") {
    return ["need", "dn", "kvs", "ways"];
  }
  if (answers.need === "kit") {
    return ["need", "voltage"];
  }
  if (answers.need === "adapter") {
    return ["need", "adapter_type"];
  }
  const steps: QuizStepId[] = ["need", "application"];
  if (answers.application === "failsafe") {
    steps.push("failsafe_type");
  }
  steps.push("voltage", "control", "damper_area", "damper_type", "damper_pressure");
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
      return "voltage";
    case "failsafe_type":
      return "voltage";
    case "voltage":
      if (answers.need === "kit") return "results";
      if (answers.need === "actuator") return "control";
      return "results";
    case "control":
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
  voltage: "voltage",
  control: "control",
  damper_area: "damperArea",
  damper_type: "damperType",
  damper_pressure: "damperPressure",
  dn: "dn",
  kvs: "kvs",
  ways: "ways",
  adapter_type: "adapterType",
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
  }
  return { answers, stepStack, phase: "questions" };
}

export function resetQuizState(): QuizState {
  return createInitialQuizState();
}

export function isQuizStarted(state: QuizState): boolean {
  return state.stepStack.length > 1 || state.phase === "results";
}
