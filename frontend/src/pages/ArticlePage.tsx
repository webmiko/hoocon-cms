import { useParams } from "react-router-dom";

/** Article detail page — stub (filled in F6). */
export function ArticlePage() {
  const { slug } = useParams<{ slug: string }>();
  return (
    <div>
      <h1>Статья: {slug}</h1>
      <p>Карточка статьи — слайс F6.</p>
    </div>
  );
}
