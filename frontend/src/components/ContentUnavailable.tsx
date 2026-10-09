import { Link } from "react-router-dom";

import { isNotFoundError } from "../utils/apiErrors";
import { Seo } from "./Seo";

type ContentUnavailableProps = {
  error: unknown;
  notFoundTitle: string;
  backTo: string;
  backLabel: string;
  className?: string;
  linkClassName?: string;
};

/**
 * Missing CMS page/article/news: always noindex (a soft 404 otherwise),
 * and network/5xx errors offer a retry instead of claiming «не найдено».
 */
export function ContentUnavailable({
  error,
  notFoundTitle,
  backTo,
  backLabel,
  className,
  linkClassName,
}: ContentUnavailableProps) {
  const missing = isNotFoundError(error);
  const title = missing ? notFoundTitle : "Не удалось загрузить страницу";
  return (
    <div className={className}>
      <Seo title={missing ? `${notFoundTitle} — 404` : title} noindex />
      <h1>{title}</h1>
      {missing ? null : (
        <p>
          Проверьте соединение и{" "}
          <button type="button" className={linkClassName} onClick={() => window.location.reload()}>
            попробуйте ещё раз
          </button>
          .
        </p>
      )}
      <Link to={backTo} className={linkClassName}>
        {backLabel}
      </Link>
    </div>
  );
}
