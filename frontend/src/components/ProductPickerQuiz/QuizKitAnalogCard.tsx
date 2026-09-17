import { Link } from "react-router-dom";

import type { QuizKitAnalogBundle, SKUList } from "../../api/client";
import { catalogPathForSku } from "../../utils/catalogPaths";
import { stockAvailabilityLabel } from "../../utils/stockAvailability";
import styles from "./ProductPickerQuiz.module.css";

type QuizKitAnalogCardProps = {
  bundle: QuizKitAnalogBundle;
};

function bundlePartLabel(role: "valve" | "drive" | "bracket"): string {
  switch (role) {
    case "valve":
      return "Кран";
    case "drive":
      return "Привод";
    case "bracket":
      return "Кронштейн";
    default:
      return "";
  }
}

function BundlePart({
  role,
  sku,
  code,
}: {
  role: "valve" | "drive" | "bracket";
  sku: SKUList;
  code?: string;
}) {
  const article = code ?? sku.sku_code;
  const stockLabel = stockAvailabilityLabel(sku.in_stock);
  return (
    <div className={styles.bundlePart}>
      <p className={styles.bundlePartRole}>{bundlePartLabel(role)}</p>
      <Link to={catalogPathForSku(sku)} className={styles.bundlePartLink}>
        {sku.name}
      </Link>
      <p className={styles.bundlePartMeta}>
        <span>{article}</span>
        <span aria-hidden="true"> · </span>
        <span>{stockLabel}</span>
      </p>
    </div>
  );
}

/** Quiz result card: bare valve + compatible drive + bracket. */
export function QuizKitAnalogCard({ bundle }: QuizKitAnalogCardProps) {
  const stockLabel = bundle.in_stock ? "В наличии" : "Под заказ";
  return (
    <article className={styles.bundleCard} data-in-stock={bundle.in_stock ? "1" : "0"}>
      <div className={styles.bundleHead}>
        <h4 className={styles.bundleTitle}>Комплект из отдельных позиций</h4>
        <p className={styles.bundleStock}>{stockLabel}</p>
      </div>
      <div className={styles.bundleParts}>
        <BundlePart role="valve" sku={bundle.valve} />
        <BundlePart role="drive" sku={bundle.drive} code={bundle.drive_code} />
        {bundle.bracket ? (
          <BundlePart
            role="bracket"
            sku={bundle.bracket}
            code={bundle.bracket_code}
          />
        ) : null}
      </div>
    </article>
  );
}
