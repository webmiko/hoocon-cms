import { useSearchParams } from "react-router-dom";

/** Search results page — stub (filled in F7). */
export function SearchPage() {
  const [params] = useSearchParams();
  const q = params.get("q") ?? "";
  return (
    <div>
      <h1>Поиск: {q}</h1>
      <p>Результаты поиска — слайс F7.</p>
    </div>
  );
}
