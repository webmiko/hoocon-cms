import type { QuizAnswers } from "./quizEngine";
import { QUIZ_RESULT_PAGE_SIZE, type CatalogQueryParams } from "./quizToCatalog";

const VALVE_FACET_KEYS = ["dn", "kvs", "ways"] as const;

/** Build query params for ``GET /api/catalog/quiz-analogs/`` (kit branch). */
export function buildQuizAnalogParams(
  answers: QuizAnswers,
  catalogParams: CatalogQueryParams,
): Record<string, string> {
  const params: Record<string, string> = {
    need: "kit",
    page_size: QUIZ_RESULT_PAGE_SIZE,
  };

  if (answers.voltage) {
    params.quiz_voltage = answers.voltage;
  }
  if (answers.control) {
    params.quiz_control = answers.control;
  }
  if (answers.auxSwitch) {
    params.quiz_aux = answers.auxSwitch;
  }

  for (const key of VALVE_FACET_KEYS) {
    const value = catalogParams[key];
    if (value) {
      params[key] = value;
    }
  }

  return params;
}

/** True when kit quiz should try component bundles instead of factory kits. */
export function shouldFetchKitAnalogs(
  need: QuizAnswers["need"],
  items: readonly { in_stock?: boolean }[],
): boolean {
  if (need !== "kit") {
    return false;
  }
  if (items.length === 0) {
    return true;
  }
  return !items.some((sku) => sku.in_stock);
}
