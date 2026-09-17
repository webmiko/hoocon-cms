import { useAsync } from "../../hooks/useAsync";
import { api, type QuizKitAnalogBundle, type SKUList } from "../../api/client";
import type { QuizAnswers } from "./quizEngine";
import {
  buildQuizAnalogParams,
  shouldFetchKitAnalogs,
} from "./quizAnalogParams";
import {
  buildCatalogParams,
  relaxCatalogParams,
  type CatalogQueryParams,
} from "./quizToCatalog";

export type QuizResultsMode = "primary" | "kit_components";

export type QuizResultsState = {
  loading: boolean;
  error: string | null;
  items: SKUList[];
  bundles: QuizKitAnalogBundle[];
  totalCount: number;
  params: CatalogQueryParams;
  relaxed: boolean;
  mode: QuizResultsMode;
  analogNote: string | null;
};

const EMPTY: QuizResultsState = {
  loading: false,
  error: null,
  items: [],
  bundles: [],
  totalCount: 0,
  params: {},
  relaxed: false,
  mode: "primary",
  analogNote: null,
};

async function fetchQuizPreview(answers: QuizAnswers): Promise<QuizResultsState> {
  const category = buildCatalogParams(answers, []).category;
  const facetsRes = await api.facets(category ? { category } : undefined);
  const strict = buildCatalogParams(answers, facetsRes.results ?? []);
  const variants = relaxCatalogParams(strict);

  let primary: QuizResultsState | null = null;
  for (let index = 0; index < variants.length; index += 1) {
    const params = variants[index]!;
    const response = await api.skus(params);
    if ((response.results?.length ?? 0) > 0 || index === variants.length - 1) {
      primary = {
        loading: false,
        error: null,
        items: response.results ?? [],
        bundles: [],
        totalCount: response.count ?? response.results?.length ?? 0,
        params,
        relaxed: index > 0,
        mode: "primary",
        analogNote: null,
      };
      break;
    }
  }

  if (primary === null) {
    primary = {
      ...EMPTY,
      params: strict,
    };
  }

  if (!shouldFetchKitAnalogs(answers.need, primary.items)) {
    const inStockItems =
      answers.need === "kit"
        ? primary.items.filter((sku) => sku.in_stock)
        : primary.items;
    return {
      ...primary,
      items: inStockItems.length > 0 ? inStockItems : primary.items,
      totalCount:
        inStockItems.length > 0 ? inStockItems.length : primary.totalCount,
    };
  }

  const analogParams = buildQuizAnalogParams(answers, primary.params);
  const analogResponse = await api.quizAnalogs(analogParams);
  if ((analogResponse.bundles?.length ?? 0) === 0) {
    return primary;
  }

  return {
    ...primary,
    items: [],
    bundles: analogResponse.bundles,
    totalCount: analogResponse.count,
    mode: "kit_components",
    analogNote: analogResponse.note || null,
  };
}

function quizResultsKey(answers: QuizAnswers): string {
  return JSON.stringify(answers);
}

/**
 * Fetch SKU preview for quiz results with progressive filter relax.
 */
export function useQuizResults(
  answers: QuizAnswers,
  enabled: boolean,
): QuizResultsState {
  const refreshKey = enabled ? quizResultsKey(answers) : "quiz-off";
  const cacheKey = enabled ? `quiz-preview:${refreshKey}` : undefined;
  const { data, loading, error } = useAsync(
    () => (enabled ? fetchQuizPreview(answers) : Promise.resolve(EMPTY)),
    refreshKey,
    cacheKey,
  );

  if (!enabled) {
    return EMPTY;
  }

  if (loading) {
    return { ...EMPTY, loading: true };
  }

  if (error) {
    return {
      loading: false,
      error: "Не удалось загрузить подборку. Откройте каталог или оставьте заявку.",
      items: [],
      bundles: [],
      totalCount: 0,
      params: buildCatalogParams(answers, []),
      relaxed: false,
      mode: "primary",
      analogNote: null,
    };
  }

  return data ?? EMPTY;
}
