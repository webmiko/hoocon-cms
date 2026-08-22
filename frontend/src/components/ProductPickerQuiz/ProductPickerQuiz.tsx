import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";

import { CatalogSkuCard } from "../CatalogSkuCard";
import {
  trackQuizComplete,
  trackQuizStart,
  trackQuizToCatalog,
  trackQuizToConsultation,
} from "../../utils/analyticsTrack";
import styles from "./ProductPickerQuiz.module.css";
import { buildQuizSummaryChips, formatQuizResultsCount, QUIZ_STEPS } from "./quizCopy";
import {
  applyQuizChoice,
  createInitialQuizState,
  getCurrentStepId,
  goBackQuizStep,
  plannedQuizSteps,
  quizProgressIndex,
  resetQuizState,
  skipQuizStep,
  type QuizState,
} from "./quizEngine";
import { iconForChoice } from "./quizChoiceIcons";
import { quizMomentEstimateNote } from "./quizMomentEstimate";
import { catalogUrlFromParams } from "./quizToCatalog";
import { useQuizResults } from "./useQuizResults";

/**
 * Home-page product picker quiz — answers → catalog parameters.
 */
export function ProductPickerQuiz() {
  const questionRef = useRef<HTMLHeadingElement>(null);
  const startedTrackedRef = useRef(false);
  const completedTrackedRef = useRef(false);
  const [state, setState] = useState<QuizState>(() => createInitialQuizState());

  const stepId =
    state.phase === "results" ? null : getCurrentStepId(state);
  const stepCopy = stepId ? QUIZ_STEPS[stepId] : null;
  const progress = quizProgressIndex(state);
  const plan = plannedQuizSteps(state.answers);
  const chips = buildQuizSummaryChips(state.answers);
  const results = useQuizResults(state.answers, state.phase === "results");
  const momentNote = quizMomentEstimateNote(state.answers);

  useEffect(() => {
    if (state.stepStack.length > 1 && !startedTrackedRef.current) {
      trackQuizStart();
      startedTrackedRef.current = true;
    }
  }, [state.stepStack.length]);

  useEffect(() => {
    if (
      state.phase === "results" &&
      !completedTrackedRef.current &&
      !results.loading
    ) {
      trackQuizComplete({
        category: results.params.category ?? "",
        count: results.totalCount,
        relaxed: results.relaxed,
      });
      completedTrackedRef.current = true;
    }
  }, [
    state.phase,
    results.loading,
    results.params.category,
    results.totalCount,
    results.relaxed,
  ]);

  useEffect(() => {
    if (state.phase === "questions" && questionRef.current) {
      questionRef.current.focus();
    }
  }, [stepId, state.phase]);

  function handleChoice(choiceId: string) {
    setState((prev) => applyQuizChoice(prev, choiceId));
  }

  function handleBack() {
    setState((prev) => goBackQuizStep(prev));
    if (state.phase === "results") {
      completedTrackedRef.current = false;
    }
  }

  function handleSkip() {
    setState((prev) => skipQuizStep(prev));
  }

  function handleReset() {
    setState(resetQuizState());
    startedTrackedRef.current = false;
    completedTrackedRef.current = false;
  }

  const catalogHref = catalogUrlFromParams(results.params);

  return (
    <section
      id="podbor"
      className={styles.section}
      aria-labelledby="podbor-heading"
      data-section="product-picker-quiz"
    >
      <div className={styles.panel}>
        <div className={styles.head}>
          <div className={styles.headCopy}>
            <p className={styles.eyebrow}>Подбор за минуту</p>
            <h2 id="podbor-heading" className={styles.title}>
              Подберём модель по вашим данным
            </h2>
            <p className={styles.lead}>
              Укажите, что знаете из проекта. Подберём модели и откроем каталог
              с подходящими для вас параметрами.
            </p>
          </div>
          {chips.length > 0 ? (
            <div className={styles.chips} aria-label="Ваш выбор">
              {chips.map((chip) => (
                <span key={chip} className={styles.chip}>
                  {chip}
                </span>
              ))}
            </div>
          ) : null}
        </div>

        {state.phase === "questions" && stepCopy ? (
          <>
            <div
              className={styles.progress}
              style={{ "--quiz-steps": plan.length } as CSSProperties}
              aria-hidden="true"
            >
              {plan.map((id, index) => {
                const done = index < progress.current - 1;
                const active = id === stepId;
                return (
                  <div key={id} className={styles.progressSegment}>
                    <span
                      className={
                        done
                          ? `${styles.progressFill} ${styles.progressFillDone}`
                          : active
                            ? `${styles.progressFill} ${styles.progressFillActive}`
                            : styles.progressFill
                      }
                    />
                  </div>
                );
              })}
            </div>

            <div className={styles.stepBody}>
              <h3
                ref={questionRef}
                className={styles.stepQuestion}
                tabIndex={-1}
              >
                {stepCopy.question}
              </h3>
              {stepCopy.lead ? (
                <p className={styles.stepLead}>{stepCopy.lead}</p>
              ) : null}

              <div className={styles.choiceGrid} role="group" aria-label={stepCopy.question}>
                {stepCopy.choices.map((choice) => {
                  const Icon = iconForChoice(choice.id);
                  return (
                    <button
                      key={choice.id}
                      type="button"
                      className={styles.choiceCard}
                      onClick={() => handleChoice(choice.id)}
                    >
                      {Icon ? (
                        <span className={styles.choiceIcon}>
                          <Icon />
                        </span>
                      ) : null}
                      <span className={styles.choiceText}>
                        <span className={styles.choiceTitle}>{choice.title}</span>
                        <span className={styles.choiceHint}>{choice.hint}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className={styles.toolbar}>
              <button
                type="button"
                className={styles.backBtn}
                onClick={handleBack}
                disabled={state.stepStack.length <= 1}
              >
                Назад
              </button>
              <div>
                {stepCopy.skippable ? (
                  <button
                    type="button"
                    className={styles.skipBtn}
                    onClick={handleSkip}
                  >
                    Пропустить
                  </button>
                ) : null}
              </div>
            </div>
          </>
        ) : null}

        {state.phase === "results" ? (
          <div className={styles.stepBody} aria-live="polite">
            <div className={styles.resultsHead}>
              <h3 className={styles.resultsTitle}>
                {results.loading
                  ? "Подбираем модели…"
                  : results.totalCount > 0
                    ? formatQuizResultsCount(results.totalCount)
                    : "По этим параметрам точных моделей нет"}
              </h3>
              {results.relaxed && !results.loading ? (
                <p className={styles.resultsNote}>
                  Часть параметров смягчили — показали близкие варианты.
                </p>
              ) : null}
              {momentNote && !results.loading ? (
                <p className={styles.resultsNote}>{momentNote}</p>
              ) : null}
            </div>

            {results.error ? (
              <p className={styles.error}>{results.error}</p>
            ) : null}

            {results.loading ? (
              <p className={styles.status}>Загружаем подборку из каталога…</p>
            ) : results.items.length > 0 ? (
              <div className={styles.resultsCarousel}>
                {results.items.map((sku) => (
                  <div key={sku.slug} className={styles.resultsSlide}>
                    <CatalogSkuCard sku={sku} omitDomId variant="carousel" />
                  </div>
                ))}
              </div>
            ) : (
              <p className={styles.status}>
                Откройте каталог или опишите задачу — инженер поможет с подбором.
              </p>
            )}

            <div className={styles.resultsActions}>
              <Link
                to={catalogHref}
                className={styles.catalogCta}
                data-brand-cta
                onClick={() => trackQuizToCatalog()}
              >
                {results.totalCount > 0
                  ? `Смотреть все ${results.totalCount} в каталоге`
                  : "Открыть каталог"}
              </Link>
              <Link
                to="/consultation?from=podbor"
                className={styles.consultLink}
                onClick={() => trackQuizToConsultation()}
              >
                Нужна помощь? Запросить консультацию
              </Link>
              <button type="button" className={styles.resetBtn} onClick={handleReset}>
                Начать заново
              </button>
              <button type="button" className={styles.backBtn} onClick={handleBack}>
                Изменить ответы
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
