import { useParams } from "react-router-dom";

/** SKU detail page — stub (filled in F5). */
export function SkuDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  return (
    <div>
      <h1>SKU: {slug}</h1>
      <p>Карточка SKU с ТТХ, файлами и CTA «Запросить КП» — слайс F5.</p>
    </div>
  );
}
