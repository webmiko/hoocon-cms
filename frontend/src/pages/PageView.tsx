import { useParams } from "react-router-dom";

/** Static CMS page — stub (filled in F6). */
export function PageView() {
  const { slug } = useParams<{ slug: string }>();
  return (
    <div>
      <h1>Страница: {slug}</h1>
      <p>Статичная CMS-страница — слайс F6.</p>
    </div>
  );
}
