import { useEffect, useId, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, type SearchSuggestItem } from "../api/client";
import { HighlightQuery } from "./HighlightQuery";
import styles from "./SiteSearchForm.module.css";

const TYPE_LABEL: Record<string, string> = {
  sku: "Товар",
  article: "Статья",
  news: "Новость",
  page: "Страница",
};

const DEBOUNCE_MS = 220;
const MIN_QUERY_LEN = 2;

type SiteSearchFormProps = {
  /** Form class from the parent module (desktop / mobile variant). */
  className?: string;
  inputClassName?: string;
  buttonClassName?: string;
  /** Extra close hook (e.g. close the mobile menu) on any navigation. */
  onNavigate?: () => void;
};

/**
 * Header search form with live suggestions.
 *
 * Debounces input, queries GET /api/search/suggest/, renders an
 * ARIA combobox dropdown (ArrowUp/Down, Enter, Escape). The last option
 * always links to the full results page. Suggest failures stay silent —
 * the plain /search navigation keeps working without JS data.
 */
export function SiteSearchForm({
  className,
  inputClassName,
  buttonClassName,
  onNavigate,
}: SiteSearchFormProps) {
  const navigate = useNavigate();
  const [value, setValue] = useState("");
  const [items, setItems] = useState<SearchSuggestItem[]>([]);
  // Layout-flipped query the server found matches for («ghbdjl» → «привод»).
  const [corrected, setCorrected] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const listId = useId();
  const abortRef = useRef<AbortController | null>(null);

  const trimmed = value.trim();
  // Option order: [did-you-mean], suggestions…, «Все результаты» → /search?q=…
  const fixOffset = corrected ? 1 : 0;
  const allIndex = fixOffset + items.length;
  const optionCount = allIndex + (trimmed ? 1 : 0);
  const expanded = open && optionCount > 0;

  useEffect(() => {
    // Queries below the floor are cleared synchronously in handleChange —
    // this effect only schedules the debounced fetch.
    if (trimmed.length < MIN_QUERY_LEN) return;
    const timer = window.setTimeout(() => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      api
        .suggest(trimmed, controller.signal)
        .then((res) => {
          setItems(res.results ?? []);
          setCorrected(res.corrected_query ?? null);
          setOpen(true);
          setActive(-1);
        })
        .catch((err: unknown) => {
          if (err instanceof DOMException && err.name === "AbortError") return;
          setItems([]);
          setCorrected(null);
        });
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [trimmed]);

  function close() {
    setOpen(false);
    setActive(-1);
  }

  function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    const next = event.target.value;
    setValue(next);
    if (next.trim().length < MIN_QUERY_LEN) {
      abortRef.current?.abort();
      setItems([]);
      setCorrected(null);
      setOpen(false);
      setActive(-1);
    }
  }

  function go(url: string) {
    close();
    onNavigate?.();
    navigate(url);
  }

  function submit() {
    if (!trimmed) return;
    close();
    onNavigate?.();
    // No trailing slash — /search/?q= costs a redirect page view.
    navigate(`/search?q=${encodeURIComponent(trimmed)}`);
  }

  function applyCorrection() {
    if (!corrected) return;
    // Replace the text; the debounced effect refetches suggestions for it.
    setValue(corrected);
    setActive(-1);
  }

  function choose(index: number) {
    if (corrected && index === 0) {
      applyCorrection();
    } else if (index < allIndex) {
      go(items[index - fixOffset].url);
    } else {
      submit();
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      if (!optionCount) return;
      event.preventDefault();
      setOpen(true);
      setActive((prev) => (prev + 1) % optionCount);
    } else if (event.key === "ArrowUp") {
      if (!optionCount) return;
      event.preventDefault();
      setActive((prev) => (prev <= 0 ? optionCount - 1 : prev - 1));
    } else if (event.key === "Escape") {
      close();
    } else if (event.key === "Enter" && expanded && active >= 0) {
      event.preventDefault();
      choose(active);
    }
  }

  return (
    <form
      className={className}
      role="search"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <input
        type="search"
        name="q"
        className={inputClassName}
        placeholder="Поиск по сайту…"
        aria-label="Поиск по сайту"
        autoComplete="off"
        role="combobox"
        aria-expanded={expanded}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${listId}-option-${active}` : undefined}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onFocus={() => {
          if (items.length) setOpen(true);
        }}
        onBlur={close}
      />
      <button type="submit" className={buttonClassName}>
        Найти
      </button>
      {expanded ? (
        <ul className={styles.list} role="listbox" id={listId}>
          {corrected ? (
            <li
              id={`${listId}-option-0`}
              role="option"
              aria-selected={active === 0}
              className={`${styles.option} ${styles.optionFix} ${active === 0 ? styles.optionActive : ""}`}
              onMouseDown={(event) => {
                event.preventDefault();
                applyCorrection();
              }}
              onMouseEnter={() => setActive(0)}
            >
              <span className={styles.optionTitle}>
                Возможно, вы имели в виду: <strong>{corrected}</strong>
              </span>
            </li>
          ) : null}
          {items.map((item, itemIndex) => {
            const index = itemIndex + fixOffset;
            return (
              <li
                key={`${item.type}-${item.url}`}
                id={`${listId}-option-${index}`}
                role="option"
                aria-selected={index === active}
                className={`${styles.option} ${index === active ? styles.optionActive : ""}`}
                onMouseDown={(event) => {
                  event.preventDefault();
                  choose(index);
                }}
                onMouseEnter={() => setActive(index)}
              >
                <span className={styles.optionType}>{TYPE_LABEL[item.type] ?? item.type}</span>
                <span className={styles.optionTitle}>
                  <HighlightQuery
                    text={item.title}
                    query={corrected ?? trimmed}
                    markClassName={styles.mark}
                  />
                </span>
              </li>
            );
          })}
          <li
            id={`${listId}-option-${allIndex}`}
            role="option"
            aria-selected={active === allIndex}
            className={`${styles.option} ${styles.optionAll} ${
              active === allIndex ? styles.optionActive : ""
            }`}
            onMouseDown={(event) => {
              event.preventDefault();
              choose(allIndex);
            }}
            onMouseEnter={() => setActive(allIndex)}
          >
            <span className={styles.optionTitle}>Все результаты по «{trimmed}» →</span>
          </li>
        </ul>
      ) : null}
    </form>
  );
}
