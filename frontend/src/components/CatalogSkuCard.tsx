import { Link } from "react-router-dom";
import type { CSSProperties } from "react";

import type { SKUList } from "../api/client";
import { CompareToggle } from "./CompareToggle";
import {
  isModulatingSignalKey,
  SignalSpecValue,
} from "./SignalSpecValue";
import { SoftBreakText } from "./SoftBreakText";
import { useMatchedPhotoWash } from "../hooks/useMatchedPhotoWash";
import { cardHighlights } from "../utils/cardHighlights";
import { catalogPathForSku } from "../utils/catalogPaths";
import { formatEditionCountLabel } from "../utils/editionCountLabel";
import { mediaPurposeFromCategory } from "../utils/mediaPurpose";
import { softBreak } from "../utils/softBreak";
import { specDisplayUnit } from "../utils/specDisplay";
import { stockAvailabilityLabel } from "../utils/stockAvailability";
import styles from "../pages/CatalogPage.module.css";

type CatalogSkuCardProps = {
  sku: SKUList;
};

/**
 * Catalog grid card with photo-edge wash behind the product cutout.
 *
 * Samples the studio backdrop into a L→R gradient for the media cell only;
 * the text block keeps the default card surface. Family Products
 * (``edition_count > 1``) show a variants line and CTA «Выбрать вариант».
 */
export function CatalogSkuCard({ sku }: CatalogSkuCardProps) {
  const purpose = mediaPurposeFromCategory(sku.category_slug);
  const imageSrc = sku.image?.image ?? null;
  const wash = useMatchedPhotoWash(imageSrc);
  const washStyle: CSSProperties | undefined = wash
    ? { background: wash.css }
    : undefined;
  const cardStyle: CSSProperties | undefined = wash
    ? ({ "--card-wash-gradient": wash.css } as CSSProperties)
    : undefined;
  const editionsLabel = formatEditionCountLabel(sku.edition_count ?? 1);
  const ctaLabel = editionsLabel ? "Выбрать вариант" : "Паспорт и ТТХ";

  return (
    <article
      className={styles.card}
      data-purpose={purpose}
      style={cardStyle}
    >
      <Link
        to={catalogPathForSku(sku)}
        className={styles.cardHit}
        aria-label={sku.name}
      />
      {imageSrc ? (
        <div
          className={styles.cardMedia}
          data-purpose={purpose}
          style={washStyle}
        >
          <CompareToggle
            className={`${styles.cardCompare} ${styles.cardInteractive}`}
            item={{
              slug: sku.slug,
              sku_code: sku.sku_code,
              name: sku.name,
              image: imageSrc,
            }}
          />
          <img
            src={imageSrc}
            alt={sku.image?.alt || sku.name}
            className={styles.cardImage}
            loading="lazy"
            decoding="async"
          />
        </div>
      ) : (
        <div className={styles.cardMediaPlaceholder} data-purpose={purpose}>
          <CompareToggle
            className={`${styles.cardCompare} ${styles.cardInteractive}`}
            item={{
              slug: sku.slug,
              sku_code: sku.sku_code,
              name: sku.name,
              image: null,
            }}
          />
        </div>
      )}
      <div className={styles.cardBody}>
        <p
          className={`${styles.cardStock} ${
            sku.in_stock ? styles.cardStockIn : styles.cardStockOut
          }`}
        >
          {stockAvailabilityLabel(sku.in_stock)}
        </p>
        <p className={`${styles.cardCode} text-tech`}>
          {softBreak(sku.sku_code)}
        </p>
        <h3 className={styles.cardTitle}>{softBreak(sku.name)}</h3>
        {editionsLabel ? (
          <p className={styles.cardEditions}>{editionsLabel}</p>
        ) : null}
        {sku.highlights && sku.highlights.length > 0 ? (
          <ul className={styles.cardSpecs}>
            {cardHighlights(sku.highlights).map((h) => {
              const unit = specDisplayUnit(h.value, h.unit);
              return (
                <li key={h.key}>
                  <span className={styles.cardSpecName}>{h.name}</span>
                  {isModulatingSignalKey(h.key) ? (
                    <SignalSpecValue
                      value={`${h.value}${unit ? ` ${unit}` : ""}`}
                      className={`${styles.cardSpecValue} ${styles.cardInteractive}`}
                    />
                  ) : (
                    <span className={styles.cardSpecValue}>
                      <SoftBreakText text={h.value} />
                      {unit ? ` ${unit}` : ""}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        ) : null}
        <div className={styles.cardFooter}>
          {sku.analog_belimo_code ? (
            <span className={`${styles.cardAnalog} text-tech`}>
              Belimo: {softBreak(sku.analog_belimo_code)}
            </span>
          ) : (
            <span className={styles.cardPriceOnRequest}>Цена по запросу</span>
          )}
          <span className={styles.cardCta}>{ctaLabel}</span>
        </div>
      </div>
    </article>
  );
}
