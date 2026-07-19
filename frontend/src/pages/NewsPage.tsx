import { useParams } from "react-router-dom";

/** News detail page — stub (filled in F6). */
export function NewsPage() {
  const { slug } = useParams<{ slug: string }>();
  return (
    <div>
      <h1>Новость: {slug}</h1>
      <p>Карточка новости — слайс F6.</p>
    </div>
  );
}
