import { Link } from "react-router-dom";

import { ProtectedProductImage } from "./ProtectedProductImage";
import { catalogPathForSku } from "../utils/catalogPaths";
import styles from "./CompatiblePositions.module.css";

export type CompatiblePosition = {
  role: "drive" | "valve" | "bracket";
  name: string;
  slug: string;
  sku_code: string;
  category_slug?: string;
  image: string | null;
};

const ROLE_TITLE: Record<CompatiblePosition["role"], string> = {
  drive: "Приводы",
  valve: "Краны",
  bracket: "Кронштейн",
};

type Props = {
  items: CompatiblePosition[];
};

/**
 * B2B cross-links on adapter / brass 8100 PDP — not marketplace «also viewed».
 */
export function CompatiblePositions({ items }: Props) {
  if (!items.length) return null;

  const roles = (["drive", "valve", "bracket"] as const).filter((role) =>
    items.some((row) => row.role === role),
  );
  const showSubheads = roles.length > 1 || roles[0] !== "bracket";

  return (
    <section
      className={`${styles.section} u-protect-content`}
      aria-labelledby="compatible-positions-heading"
    >
      <h2 id="compatible-positions-heading" className={styles.title}>
        Совместимые позиции
      </h2>
      {roles.map((role) => {
        const rows = items.filter((row) => row.role === role);
        return (
          <div key={role} className={styles.group}>
            {showSubheads ? (
              <h3 className={styles.groupTitle}>{ROLE_TITLE[role]}</h3>
            ) : null}
            <ul className={styles.list}>
              {rows.map((sku) => (
                <li key={`${sku.role}-${sku.slug}`}>
                  <Link
                    to={catalogPathForSku(sku)}
                    className={styles.link}
                  >
                    {sku.image ? (
                      <ProtectedProductImage
                        frameClassName={styles.image}
                        className="u-protect-media"
                        compact
                        src={sku.image}
                        alt=""
                        loading="lazy"
                      />
                    ) : (
                      <div className={styles.imagePh} aria-hidden />
                    )}
                    <span className={styles.code}>{sku.sku_code}</span>
                    <span className={styles.name}>{sku.name}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </section>
  );
}
