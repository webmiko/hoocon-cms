import type { CatalogFacet } from "../../api/client";
import { catalogCategoryPath } from "../../utils/catalogPaths";
import { QUIZ_CATEGORY } from "./quizCategories";
import type { QuizAnswers } from "./quizEngine";
import {
  facetValuesForKey,
  matchAreaForMomentNmFacet,
  matchControlFacet,
  matchDnFacet,
  matchKvsFacet,
  matchMomentNmFacet,
  matchVoltageFacet,
  matchWaysFacet,
} from "./quizFacetMatch";
import { estimateRequiredMomentNm } from "./quizMomentEstimate";

export const QUIZ_RESULT_PAGE_SIZE = "6";

export type CatalogQueryParams = Record<string, string>;

/** Resolve target category slug from quiz answers. */
export function resolveQuizCategory(answers: QuizAnswers): string {
  switch (answers.need) {
    case "ball_valve":
      return QUIZ_CATEGORY.ballValve;
    case "kit":
      return QUIZ_CATEGORY.kit;
    case "adapter":
      return QUIZ_CATEGORY.adapter;
    case "actuator":
    default:
      break;
  }

  if (answers.application === "fire") {
    return QUIZ_CATEGORY.fire;
  }
  if (answers.application === "smoke") {
    return QUIZ_CATEGORY.smoke;
  }
  if (answers.application === "fast") {
    return QUIZ_CATEGORY.fast;
  }
  if (answers.application === "failsafe") {
    if (answers.failsafeType === "electronic") {
      return QUIZ_CATEGORY.electronic;
    }
    return QUIZ_CATEGORY.spring;
  }
  return QUIZ_CATEGORY.general;
}

/** Build API / catalog query params from quiz answers and category facets. */
export function buildCatalogParams(
  answers: QuizAnswers,
  facets: readonly CatalogFacet[],
): CatalogQueryParams {
  const category = resolveQuizCategory(answers);
  const params: CatalogQueryParams = {
    category,
    page: "1",
    page_size: QUIZ_RESULT_PAGE_SIZE,
  };

  if (answers.voltage && answers.voltage !== "skip") {
    const value = matchVoltageFacet(
      facetValuesForKey(facets, "voltage"),
      answers.voltage,
    );
    if (value) {
      params.voltage = value;
    }
  }

  if (answers.need === "actuator") {
    if (answers.control && answers.control !== "skip") {
      const value = matchControlFacet(
        facetValuesForKey(facets, "control"),
        answers.control,
      );
      if (value) {
        params.control = value;
      }
    }
    const estimatedNm = estimateRequiredMomentNm(answers);
    if (estimatedNm !== null) {
      const momentValue = matchMomentNmFacet(
        facetValuesForKey(facets, "moment"),
        estimatedNm,
      );
      if (momentValue) {
        params.moment = momentValue;
      }
      const areaValue = matchAreaForMomentNmFacet(
        facetValuesForKey(facets, "area"),
        estimatedNm,
      );
      if (areaValue) {
        params.area = areaValue;
      }
    }
  }

  if (answers.need === "ball_valve") {
    if (answers.dn && answers.dn !== "skip") {
      const value = matchDnFacet(facetValuesForKey(facets, "dn"), answers.dn);
      if (value) {
        params.dn = value;
      }
    }
    if (answers.kvs && answers.kvs !== "skip") {
      const value = matchKvsFacet(
        facetValuesForKey(facets, "kvs"),
        answers.kvs,
      );
      if (value) {
        params.kvs = value;
      }
    }
    if (answers.ways && answers.ways !== "skip") {
      const value = matchWaysFacet(
        facetValuesForKey(facets, "ways"),
        answers.ways,
      );
      if (value) {
        params.ways = value;
      }
    }
  }

  if (answers.need === "adapter" && answers.adapterType) {
    if (answers.adapterType === "br_m") {
      params.q = "BR-M";
    }
    if (answers.adapterType === "br_ml") {
      params.q = "BR-ML";
    }
  }

  return params;
}

const RELAX_ORDER = [
  "area",
  "moment",
  "control",
  "voltage",
  "ways",
  "kvs",
  "dn",
  "q",
] as const;

/** Progressive relax variants when the strict filter set returns zero SKUs. */
export function relaxCatalogParams(
  params: CatalogQueryParams,
): CatalogQueryParams[] {
  const variants: CatalogQueryParams[] = [params];
  let current = { ...params };

  for (const key of RELAX_ORDER) {
    if (!(key in current)) {
      continue;
    }
    const next = { ...current };
    delete next[key];
    current = next;
    variants.push({ ...current });
  }

  return variants;
}

/** Catalog path + query string for React Router navigation. */
export function catalogUrlFromParams(params: CatalogQueryParams): string {
  const category = params.category ?? "";
  const path = catalogCategoryPath(category);
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (key === "category" || key === "page" || key === "page_size") {
      continue;
    }
    if (value) {
      search.set(key, value);
    }
  }
  const qs = search.toString();
  return qs ? `${path}?${qs}` : path;
}
