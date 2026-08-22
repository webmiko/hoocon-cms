import { Link, useLocation } from "react-router-dom";
import type { CSSProperties } from "react";

import type { SKUList } from "../api/client";
import { CompareToggle } from "./CompareToggle";
import { ProtectedProductImage } from "./ProtectedProductImage";
import { SignalSpecValue } from "./SignalSpecValue";
import { SoftBreakText } from "./SoftBreakText";
import { cardHighlights, compactCardSpecName } from "../utils/cardHighlights";
import { isModulatingSignalKey } from "../utils/isModulatingSignalKey";
import { catalogPathForSku } from "../utils/catalogPaths";
import {
  catalogFocusPath,
  catalogSkuDomId,
  saveCatalogFocus,
} from "../utils/catalogFocus";
import {
  protectedContentHandlers,
  protectedMediaImgProps,
} from "../utils/contentProtection";
import { formatEditionCountLabel } from "../utils/editionCountLabel";
import { useNormalizedPhotoScale } from "../hooks/useNormalizedPhotoScale";
import { mediaPurposeFromCategory } from "../utils/mediaPurpose";
import { photoScalePlanFromHighlights } from "../utils/productPhotoScale";
import { productCardImageSrc } from "../utils/productImageSrc";
import { softBreak } from "../utils/softBreak";
import { specDisplayUnit } from "../utils/specDisplay";
import { stockAvailabilityLabel } from "../utils/stockAvailability";
import styles from "../pages/CatalogPage.module.css";

type CatalogSkuCardProps = {
  sku: SKUList;
  /** Skip ``id`` when the card is cloned (e.g. infinite carousel). */
  omitDomId?: boolean;
  /** Home / quiz carousels: photo above copy, fixed slide height. */
  variant?: "default" | "vertical" | "carousel";
};

/**
 * Catalog grid card with theme photo wash behind the product cutout.
 *
 * Light gray / dark graphite via ``--photo-wash``. Family Products
 * (``edition_count > 1``) show a variants line and CTA «Выбрать вариант».
 * Photo save / text copy are deterred via contentProtection helpers.
 */
export function CatalogSkuCard({
  sku,
  omitDomId = false,
  variant = "default",
}: CatalogSkuCardProps) {
  const location = useLocation();
  const purpose = mediaPurposeFromCategory(sku.category_slug);
  const imageSrc = productCardImageSrc(sku.image);
  const photoPlan = photoScalePlanFromHighlights(sku.highlights, sku.sku_code);
  const photoScale = useNormalizedPhotoScale(
    imageSrc,
    photoPlan.target,
    photoPlan.maxCssScale,
  );
  const editionsLabel = formatEditionCountLabel(sku.edition_count ?? 1);
  const ctaLabel = editionsLabel ? "Выбрать вариант" : "Паспорт и характеристики";
  const skuHref = catalogPathForSku(sku);
  const highlightMax = variant === "carousel" ? 4 : undefined;
  const cardClass =
    variant === "vertical"
      ? `${styles.card} ${styles.cardVertical} u-protect-content`
      : variant === "carousel"
        ? `${styles.card} ${styles.cardCarousel} u-protect-content`
        : `${styles.card} u-protect-content`;

  function rememberFocus() {
    saveCatalogFocus({
      path: catalogFocusPath(location.pathname, location.search),
      slug: sku.slug,
      y: window.scrollY,
    });
  }

  return (
    <article
      id={omitDomId ? undefined : catalogSkuDomId(sku.slug)}
      className={cardClass}
      data-purpose={purpose}
      {...protectedContentHandlers}
    >
      {imageSrc ? (
        <div
          className={`${styles.cardMedia} u-protect-media`}
          data-purpose={purpose}
          style={{ "--photo-scale": String(photoScale) } as CSSProperties}
          onContextMenu={protectedMediaImgProps.onContextMenu}
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
          <ProtectedProductImage
            src={imageSrc}
            alt=""
            className={styles.cardImage}
            loading="lazy"
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
        <div className={styles.cardMetaRow}>
          <p
            className={`${styles.cardStock} ${
              sku.in_stock ? styles.cardStockIn : styles.cardStockOut
            }`}
          >
            {stockAvailabilityLabel(sku.in_stock)}
          </p>
          {sku.is_new ? <p className={styles.cardNew}>Новое</p> : null}
        </div>
        <p className={`${styles.cardCode} text-tech`}>
          {softBreak(sku.sku_code)}
        </p>
        <h3 className={styles.cardTitle}>
          <Link
            to={skuHref}
            className={styles.cardTitleLink}
            onPointerDown={rememberFocus}
            onClick={rememberFocus}
          >
            {softBreak(sku.name)}
            <span className="sr-only">. {ctaLabel}</span>
          </Link>
        </h3>
        {editionsLabel ? (
          <p className={styles.cardEditions}>{editionsLabel}</p>
        ) : null}
        {sku.highlights && sku.highlights.length > 0 ? (
          <ul className={styles.cardSpecs} role="list">
            {cardHighlights(sku.highlights, highlightMax).map((h) => {
              const unit = specDisplayUnit(h.value, h.unit);
              const label = compactCardSpecName(h.name);
              return (
                <li key={h.key}>
                  <span className={styles.cardSpecName}>{label}</span>
                  {isModulatingSignalKey(h.key) ? (
                    <SignalSpecValue
                      value={`${h.value}${unit ? ` ${unit}` : ""}`}
                      maInStock={Boolean(sku.in_stock_ma)}
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
          <span className={styles.cardCta} aria-hidden="true">
            {ctaLabel}
          </span>
        </div>
      </div>
    </article>
  );
}
