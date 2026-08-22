import { useAsync } from "../../hooks/useAsync";
import { api, type SKUList } from "../../api/client";
import type { QuizAnswers } from "./quizEngine";
import {
  buildCatalogParams,
  relaxCatalogParams,
  type CatalogQueryParams,
} from "./quizToCatalog";

export type QuizResultsState = {
  loading: boolean;
  error: string | null;
  items: SKUList[];
  totalCount: number;
  params: CatalogQueryParams;
  relaxed: boolean;
};

const EMPTY: QuizResultsState = {
  loading: false,
  error: null,
  items: [],
  totalCount: 0,
  params: {},
  relaxed: false,
};

async function fetchQuizPreview(answers: QuizAnswers): Promise<QuizResultsState> {
  const category = buildCatalogParams(answers, []).category;
  const facetsRes = await api.facets(category ? { category } : undefined);
  const strict = buildCatalogParams(answers, facetsRes.results ?? []);
  const variants = relaxCatalogParams(strict);

  for (let index = 0; index < variants.length; index += 1) {
    const params = variants[index]!;
    const response = await api.skus(params);
    if ((response.results?.length ?? 0) > 0 || index === variants.length - 1) {
      return {
        loading: false,
        error: null,
        items: response.results ?? [],
        totalCount: response.count ?? response.results?.length ?? 0,
        params,
        relaxed: index > 0,
      };
    }
  }

  return {
    ...EMPTY,
    params: strict,
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
      totalCount: 0,
      params: buildCatalogParams(answers, []),
      relaxed: false,
    };
  }

  return data ?? EMPTY;
}
