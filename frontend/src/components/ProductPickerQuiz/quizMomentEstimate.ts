import type {
  QuizAnswers,
  QuizDamperArea,
  QuizDamperPressure,
  QuizDamperType,
} from "./quizEngine";

/** Hoocon catalog moment ladder (Nm). */
export const HOOCON_MOMENT_LADDER = [
  2, 4, 5, 6, 8, 10, 16, 20, 24, 32, 40,
] as const;

const AREA_S_M2: Record<Exclude<QuizDamperArea, "skip">, number> = {
  up_to_0_3: 0.3,
  "0_3_0_6": 0.6,
  "0_6_1_0": 1.0,
  "1_0_1_6": 1.6,
  "1_6_2_5": 2.5,
  "2_5_4_0": 4.0,
  over_4: 5.0,
};

const PRESSURE_PA: Record<Exclude<QuizDamperPressure, "skip">, number> = {
  low: 250,
  medium: 450,
  high: 800,
  very_high: 1200,
};

const TYPE_K: Record<Exclude<QuizDamperType, "skip">, number> = {
  round: 1.0,
  rectangular: 1.4,
  gate: 1.8,
};

const DEFAULT_PRESSURE_PA = PRESSURE_PA.medium;
const DEFAULT_TYPE_K = TYPE_K.rectangular;
const DEFAULT_MARGIN_K = 1.3;
const HIGH_PRESSURE_MARGIN_K = 1.4;

/**
 * Parse numeric m² from facet labels like ``до 1,0 м²``.
 */
export function parseAreaM2(value: string): number | null {
  const match = value.match(/(\d+(?:[.,]\d+)?)\s*м\s*²/i);
  if (!match?.[1]) {
    return null;
  }
  return Number.parseFloat(match[1].replace(",", "."));
}

/** Parse numeric Nm from a facet label like ``10 Нм``. */
export function parseMomentNm(value: string): number | null {
  const match = value.match(/(\d+(?:[.,]\d+)?)\s*н\s*·?\s*м/i);
  if (!match?.[1]) {
    return null;
  }
  return Number.parseFloat(match[1].replace(",", "."));
}

/** Round required torque up to the next Hoocon catalog step (with margin bump). */
export function ceilToMomentLadder(requiredNm: number): number {
  for (let index = 0; index < HOOCON_MOMENT_LADDER.length; index += 1) {
    const step = HOOCON_MOMENT_LADDER[index]!;
    if (step >= requiredNm) {
      const next = HOOCON_MOMENT_LADDER[index + 1];
      if (next !== undefined && requiredNm > step * 0.85) {
        return next;
      }
      return step;
    }
  }
  return HOOCON_MOMENT_LADDER[HOOCON_MOMENT_LADDER.length - 1]!;
}

/**
 * Estimate required torque (Nm) from damper area, pressure and blade type.
 *
 * Uses the site article orientir: M = S × P × Kтип × Kзапас / 100.
 */
export function estimateRequiredMomentNm(answers: QuizAnswers): number | null {
  if (!answers.damperArea || answers.damperArea === "skip") {
    return null;
  }

  const areaM2 = AREA_S_M2[answers.damperArea];
  const pressurePa =
    answers.damperPressure && answers.damperPressure !== "skip"
      ? PRESSURE_PA[answers.damperPressure]
      : DEFAULT_PRESSURE_PA;
  const typeK =
    answers.damperType && answers.damperType !== "skip"
      ? TYPE_K[answers.damperType]
      : DEFAULT_TYPE_K;
  const marginK =
    answers.damperPressure === "very_high"
      ? HIGH_PRESSURE_MARGIN_K
      : DEFAULT_MARGIN_K;

  const raw = (areaM2 * pressurePa * typeK * marginK) / 100;
  return ceilToMomentLadder(raw);
}

/** Human-readable note for the results step when torque was derived. */
export function quizMomentEstimateNote(answers: QuizAnswers): string | null {
  const nm = estimateRequiredMomentNm(answers);
  if (nm === null) {
    return null;
  }
  return `Расчётный ориентир: ${nm} Нм. Итоговый выбор — по паспорту заслонки.`;
}
