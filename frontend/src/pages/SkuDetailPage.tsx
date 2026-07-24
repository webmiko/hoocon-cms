import { useMemo, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import {
  ImageLightbox,
  type LightboxImage,
} from "../components/ImageLightbox";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { LeadForm } from "../components/LeadForm";
import { Seo } from "../components/Seo";
import { buildProductJsonLd, buildBreadcrumbJsonLd } from "../utils/jsonLd";
import { parseProductDescription } from "../utils/parseDescription";
import { InstructionText } from "../components/InstructionText";
import {
  isModulatingSignalKey,
  SignalSpecValue,
} from "../components/SignalSpecValue";
import { CompareToggle } from "../components/CompareToggle";
import { PhotoWash } from "../components/PhotoWash";
import { SoftBreakText } from "../components/SoftBreakText";
import { softBreak } from "../utils/softBreak";
import { paraphraseSkuLead } from "../utils/paraphraseSkuLead";
import { specDisplayUnit } from "../utils/specDisplay";
import { stockAvailabilityLabel } from "../utils/stockAvailability";
import { skuSeoDescription, skuSeoTitlePartial } from "../utils/seoMeta";
import { mediaPurposeFromCategory } from "../utils/mediaPurpose";
import {
  catalogCategoryPath,
  catalogPathForSku,
  catalogSkuPath,
} from "../utils/catalogPaths";
import {
  isTechnicalDiagram,
  sizeDiagramSrcForTheme,
} from "../utils/sizeDiagramTheme";
import { useTheme } from "../theme/ThemeContext";
import { api } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import styles from "./SkuDetailPage.module.css";

/** File item from SKU detail (drf-spectacular types files as unknown[]). */
interface SkuFile {
  id: number;
  title: string;
  file: string;
  file_type: string;
  sort_order: number;
}

interface SkuImage {
  id?: number;
  image: string;
  alt?: string;
}

type TabId = "description" | "instructions" | "specs" | "analogs";

/** Spec cell: Y/U with FAQ link on «спецзаказ», else SoftBreak + unit. */
function SpecAttrValue({
  slug,
  value,
  unit,
  valueClassName,
  unitClassName,
}: {
  slug: string;
  value: string;
  unit?: string | null;
  valueClassName: string;
  unitClassName: string;
}) {
  const displayUnit = specDisplayUnit(value, unit ?? undefined);
  const display = `${value}${displayUnit ? ` ${displayUnit}` : ""}`;
  if (isModulatingSignalKey(slug) || value.includes("(спецзаказ)")) {
    return <SignalSpecValue value={display} className={valueClassName} />;
  }
  return (
    <span className={valueClassName}>
      <SoftBreakText text={value} />
      {displayUnit ? (
        <span className={unitClassName}> {displayUnit}</span>
      ) : null}
    </span>
  );
}

/** True when category blurb is not a foreign-series dump (e.g. HVA on DA8MQU). */
function categoryCopyFitsSku(
  categoryDescription: string,
  skuCode: string,
): boolean {
  const text = categoryDescription || "";
  const code = (skuCode || "").toUpperCase();
  if (!text.trim() || !code) return Boolean(text.trim());
  // Concrete model refs like HVA24S-5 / DA8MQU24-D
  const models = text.match(
    /\b[A-Z]{2,6}\d{0,3}[A-Z]{0,4}\d{0,3}S?[-\s]?\d*[A-Z]{0,2}\b/gi,
  );
  if (!models?.length) return true;
  return models.some((m) => {
    const token = m.toUpperCase().replace(/[\s-]/g, "");
    const skuCompact = code.replace(/[\s-]/g, "");
    // Family prefix: HVA, DA8MQU, DA8MU…
    const family = token.replace(/\d+[A-Z]*$/i, "").replace(/\d+$/g, "");
    if (family.length >= 3 && skuCompact.includes(family)) return true;
    return skuCompact.includes(token.slice(0, Math.min(6, token.length)));
  });
}

/** True when two copy blocks share the same series lead (avoid double Описание). */
function descriptionsOverlap(a: string, b: string): boolean {
  const norm = (s: string) =>
    s
      .toLowerCase()
      .replace(/[«»""„]/g, "")
      .replace(/\s+/g, " ")
      .trim();
  const na = norm(a);
  const nb = norm(b);
  if (!na || !nb) return false;
  const window = 160;
  const wa = na.slice(0, window);
  const wb = nb.slice(0, window);
  if (wa === wb) return true;
  const probe = 100;
  return (
    na.includes(wb.slice(0, probe)) || nb.includes(wa.slice(0, probe))
  );
}
/**
 * SKU detail page (PDP): tabs as on Tilda (Описание / Инструкция /
 * Характеристики / Аналоги) + documents + RFQ.
 *
 * Series-level copy comes from the category; model-specific from the SKU.
 */
export function SkuDetailPage() {
  const { categorySlug, skuSlug } = useParams<{
    categorySlug: string;
    skuSlug: string;
  }>();
  const slug = skuSlug;
  const { resolved: theme } = useTheme();
  const { data: sku, loading, error } = useAsync(
    () => api.skuDetail(slug!),
    [slug],
  );
  const [tab, setTab] = useState<TabId>("description");
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  const files: SkuFile[] = useMemo(
    () => ((sku?.files ?? []) as unknown[] as SkuFile[]),
    [sku],
  );

  const mediaPurpose = useMemo(
    () => mediaPurposeFromCategory(sku?.category_slug),
    [sku?.category_slug],
  );

  const galleryImages: LightboxImage[] = useMemo(() => {
    if (!sku) return [];
    const mapImg = (img: SkuImage): LightboxImage => {
      const alt = img.alt || sku.name;
      return {
        src: sizeDiagramSrcForTheme(img.image, theme),
        alt,
      };
    };
    if ("images" in sku && Array.isArray(sku.images) && sku.images.length > 0) {
      return (sku.images as SkuImage[]).map(mapImg);
    }
    if (
      "image" in sku &&
      sku.image &&
      typeof sku.image === "object" &&
      "image" in sku.image &&
      typeof (sku.image as SkuImage).image === "string"
    ) {
      return [mapImg(sku.image as SkuImage)];
    }
    return [];
  }, [sku, theme]);

  if (loading) {
    return <p className={styles.status}>Загрузка…</p>;
  }

  if (error || !sku) {
    return (
      <div className={styles.notFound}>
        <Seo
          title="Товар не найден"
          path={
            categorySlug && slug
              ? catalogSkuPath(categorySlug, slug)
              : "/catalog"
          }
          noindex
        />
        <h1>Товар не найден</h1>
        <p>Возможно, страница была перемещена или удалена.</p>
        <Link to="/catalog" className={styles.link}>
          ← Вернуться в каталог
        </Link>
      </div>
    );
  }

  const canonicalPath = catalogPathForSku(sku);
  if (
    categorySlug &&
    sku.category_slug &&
    categorySlug !== sku.category_slug
  ) {
    return <Navigate to={canonicalPath} replace />;
  }

  const jsonLd = buildProductJsonLd({
    name: sku.name,
    slug: sku.slug,
    sku_code: sku.sku_code,
    description: sku.description,
    price: "price" in sku ? sku.price : null,
    price_on_request: sku.price_on_request,
    category_name: sku.category_name || sku.category_slug,
    category_slug: sku.category_slug,
  });

  const descriptionBody =
    (sku.description ?? "").trim() ||
    ("lead" in sku && sku.lead ? paraphraseSkuLead(sku.lead) : "");

  const tabs: Array<{ id: TabId; label: string; available: boolean }> = [
    {
      id: "description",
      label: "Описание",
      available: Boolean(descriptionBody || sku.category_description),
    },
    {
      id: "instructions",
      label: "Инструкция",
      available: Boolean(sku.category_instructions),
    },
    {
      id: "specs",
      label: "Характеристики",
      available: Boolean(
        sku.specs_text ||
          (sku.attribute_groups && sku.attribute_groups.length > 0) ||
          (sku.attributes && sku.attributes.length > 0),
      ),
    },
    {
      id: "analogs",
      label: "Аналоги",
      available: Boolean(sku.analogs_text),
    },
  ];
  const visibleTabs = tabs.filter((t) => t.available);
  const activeTab = visibleTabs.some((t) => t.id === tab)
    ? tab
    : (visibleTabs[0]?.id ?? "description");

  return (
    <div className={styles.detail}>
      <Seo
        title={skuSeoTitlePartial(sku.sku_code, sku.highlights)}
        description={skuSeoDescription(sku.sku_code, sku.category_name)}
        path={canonicalPath}
        jsonLd={[
          jsonLd,
          buildBreadcrumbJsonLd([
            { name: "Главная", path: "/" },
            { name: "Каталог", path: "/catalog" },
            ...(sku.category_slug
              ? [
                  {
                    name: sku.category_name || sku.category_slug,
                    path: catalogCategoryPath(sku.category_slug),
                  },
                ]
              : []),
            { name: sku.name, path: canonicalPath },
          ]),
        ]}
        ogType="product"
      />
      <Breadcrumbs
        items={[
          { label: "Главная", to: "/" },
          { label: "Каталог", to: "/catalog" },
          ...(sku.category_slug
            ? [
                {
                  label: sku.category_name || sku.category_slug,
                  to: catalogCategoryPath(sku.category_slug),
                },
              ]
            : []),
          { label: sku.sku_code, tech: true },
        ]}
      />

      <div className={styles.hero}>
        <PhotoWash
          className={styles.heroMedia}
          data-purpose={mediaPurpose}
          src={galleryImages[0]?.src}
          backdrop={
            galleryImages[0] &&
            isTechnicalDiagram(galleryImages[0].src, galleryImages[0].alt)
              ? "white"
              : "auto"
          }
        >
          {galleryImages.length > 0 ? (
            <button
              type="button"
              className={styles.heroZoomTrigger}
              onClick={() => setLightboxIndex(0)}
              aria-label="Увеличить фото"
            >
              <img
                src={galleryImages[0].src}
                alt={galleryImages[0].alt}
                className={styles.heroImage}
                loading="eager"
                decoding="async"
              />
            </button>
          ) : (
            <div className={styles.heroPlaceholder} aria-hidden="true" />
          )}
        </PhotoWash>

        <div className={styles.heroMain}>
          <h1 className={styles.title}>{softBreak(sku.name)}</h1>
          {"lead" in sku && sku.lead ? (
            <p className={styles.heroLead}>{softBreak(sku.lead)}</p>
          ) : null}
          <p className={`${styles.skuCode} text-tech`}>
            Артикул: {softBreak(sku.sku_code)}
          </p>
          <p
            className={`${styles.stockLabel} ${
              sku.in_stock ? styles.stockIn : styles.stockOut
            }`}
          >
            {stockAvailabilityLabel(sku.in_stock)}
          </p>
          {sku.analog_belimo_code ? (
            <p className={`${styles.analog} text-tech`}>
              Аналог Belimo: <strong>{softBreak(sku.analog_belimo_code)}</strong>
            </p>
          ) : null}

          {sku.highlights && sku.highlights.length > 0 ? (
            <ul className={styles.heroSpecs}>
              {sku.highlights.map((h) => {
                const unit = specDisplayUnit(h.value, h.unit);
                const display = `${h.value}${unit ? ` ${unit}` : ""}`;
                return (
                  <li key={h.key}>
                    <span className={styles.heroSpecLabel}>{h.name}:</span>{" "}
                    <strong>
                      {isModulatingSignalKey(h.key) ? (
                        <SignalSpecValue value={display} />
                      ) : (
                        <>
                          <SoftBreakText text={h.value} />
                          {unit ? ` ${unit}` : ""}
                        </>
                      )}
                    </strong>
                  </li>
                );
              })}
            </ul>
          ) : null}

          <div className={styles.heroActions}>
            <div className={styles.priceBlock}>
              {"price" in sku && sku.price ? (
                <p className={styles.price}>{sku.price} ₽</p>
              ) : (
                <p className={styles.priceOnRequest}>Цена по запросу</p>
              )}
            </div>
            <CompareToggle
              variant="button"
              item={{
                slug: sku.slug,
                sku_code: sku.sku_code,
                name: sku.name,
                image: sku.images?.[0]?.image ?? sku.image?.image ?? null,
              }}
            />
            <a href="#rfq" className={styles.heroCta}>
              Запросить цену
            </a>
          </div>
        </div>
      </div>

      {galleryImages.length > 1 ? (
        <div className={styles.gallery} aria-label="Дополнительные фотографии">
          {galleryImages.slice(1).map((item, offset) => {
            const fullIndex = offset + 1;
            return (
              <PhotoWash
                key={`${item.src}-${fullIndex}`}
                className={styles.galleryItem}
                data-purpose={mediaPurpose}
                src={item.src}
                backdrop={
                  isTechnicalDiagram(item.src, item.alt) ? "white" : "auto"
                }
              >
                <button
                  type="button"
                  className={styles.galleryZoomTrigger}
                  onClick={() => setLightboxIndex(fullIndex)}
                  aria-label={`Увеличить фото ${fullIndex + 1}`}
                >
                  <img
                    src={item.src}
                    alt={item.alt}
                    className={
                      isTechnicalDiagram(item.src, item.alt)
                        ? `${styles.galleryImage} ${styles.galleryImageDiagram}`
                        : styles.galleryImage
                    }
                    loading="lazy"
                    decoding="async"
                  />
                </button>
              </PhotoWash>
            );
          })}
        </div>
      ) : null}

      {lightboxIndex !== null && galleryImages.length > 0 ? (
        <ImageLightbox
          images={galleryImages}
          index={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          onIndexChange={setLightboxIndex}
        />
      ) : null}

      <div className={styles.contentGrid}>
        <div className={styles.contentPrimary}>
          {visibleTabs.length > 0 ? (
            <div className={styles.tabs}>
              <div className={styles.tabList} role="tablist" aria-label="Разделы">
                {visibleTabs.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    role="tab"
                    aria-selected={activeTab === item.id}
                    className={
                      activeTab === item.id ? styles.tabActive : styles.tab
                    }
                    onClick={() => setTab(item.id)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>

              <div className={styles.tabPanel} role="tabpanel">
                {activeTab === "description" ? (
                  <section className={styles.section}>
                    {descriptionBody ? (
                      <StructuredText text={descriptionBody} />
                    ) : null}
                    {sku.category_description &&
                    sku.category_description !== descriptionBody &&
                    !descriptionsOverlap(
                      sku.category_description,
                      descriptionBody,
                    ) &&
                    categoryCopyFitsSku(
                      sku.category_description,
                      sku.sku_code,
                    ) ? (
                      <div className={styles.seriesBlock}>
                        <h2 className={styles.descDocTitle}>О линейке продукции</h2>
                        <StructuredText text={sku.category_description} />
                      </div>
                    ) : null}
                  </section>
                ) : null}

                {activeTab === "instructions" && sku.category_instructions ? (
                  <section className={styles.section}>
                    <InstructionText
                      text={sku.category_instructions}
                      styles={{
                        lead: styles.descLead,
                        quote: styles.descQuote,
                        docTitle: styles.descDocTitle,
                        section: styles.descSection,
                        subsection: styles.descSubsection,
                        list: styles.descList,
                      }}
                    />
                  </section>
                ) : null}

                {activeTab === "specs" ? (
                  <section className={styles.section}>
                    {(sku.attribute_groups && sku.attribute_groups.length > 0
                      ? sku.attribute_groups
                      : null
                    )?.map((group) => (
                      <div key={group.key} className={styles.specGroup}>
                        <h3 className={styles.specGroupTitle}>{group.title}</h3>
                        <ul className={styles.specCards}>
                          {group.items
                            .filter((attr, index, all) => {
                              const key = `${attr.name}|${attr.value}`.toLowerCase();
                              return (
                                all.findIndex(
                                  (other) =>
                                    `${other.name}|${other.value}`.toLowerCase() ===
                                    key,
                                ) === index
                              );
                            })
                            .map((attr) => (
                              <li
                                key={`${attr.slug}-${attr.value}`}
                                className={styles.specCard}
                              >
                                <span className={styles.specName}>
                                  {softBreak(attr.name)}
                                </span>
                                <SpecAttrValue
                                  slug={attr.slug}
                                  value={String(attr.value)}
                                  unit={attr.unit}
                                  valueClassName={styles.specValue}
                                  unitClassName={styles.specUnit}
                                />
                              </li>
                            ))}
                        </ul>
                      </div>
                    ))}
                    {!sku.attribute_groups?.length &&
                    sku.attributes &&
                    sku.attributes.length > 0 ? (
                      <ul className={styles.specCards}>
                        {sku.attributes
                          .filter((attr, index, all) => {
                            const key = `${attr.name}|${attr.value}`.toLowerCase();
                            return (
                              all.findIndex(
                                (other) =>
                                  `${other.name}|${other.value}`.toLowerCase() ===
                                  key,
                              ) === index
                            );
                          })
                          .map((attr) => (
                            <li
                              key={`${attr.slug}-${attr.value}`}
                              className={styles.specCard}
                            >
                              <span className={styles.specName}>
                                {softBreak(attr.name)}
                              </span>
                              <SpecAttrValue
                                slug={attr.slug}
                                value={String(attr.value)}
                                unit={attr.unit}
                                valueClassName={styles.specValue}
                                unitClassName={styles.specUnit}
                              />
                            </li>
                          ))}
                      </ul>
                    ) : null}
                    {sku.specs_text &&
                    !sku.attribute_groups?.length &&
                    !(sku.attributes && sku.attributes.length > 0) ? (
                      <div className={styles.specsProse}>
                        <StructuredText text={sku.specs_text} />
                      </div>
                    ) : null}
                  </section>
                ) : null}

                {activeTab === "analogs" && sku.analogs_text ? (
                  <section className={styles.section}>
                    <StructuredText text={sku.analogs_text} />
                  </section>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>

        <aside className={styles.contentAside}>
          {files.length > 0 && (
            <section className={styles.section}>
              <h2 className={styles.sectionTitle}>Документы</h2>
              <ul className={styles.fileList}>
                {files.map((file) => (
                  <li key={file.id} className={styles.fileItem}>
                    <a href={file.file} className={styles.fileLink} download>
                      <span className={styles.fileIcon}>PDF</span>
                      <span className={styles.fileTitle}>{file.title}</span>
                      <span className={styles.fileType}>{file.file_type}</span>
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section id="rfq" className={styles.ctaSection}>
            <h2 className={styles.ctaTitle}>Запросить коммерческое предложение</h2>
            <p className={styles.ctaText}>
              Отправьте заявку — подготовим КП на {sku.name}
              {" "}
              (арт. {sku.sku_code}). Ответим до 2 рабочих часов с ценой и сроком
              или уточняющими вопросами по ТТХ.
            </p>
            <p className={styles.ctaSla}>
              Заявка уходит на sales@hoocon.ru. Публичного прайса нет — цена
              зависит от объёма.
            </p>
            <LeadForm
              leadType="rfq"
              skuSlug={sku.slug}
              skuName={sku.name}
              ballValveKit={
                "ball_valve_kit" in sku && sku.ball_valve_kit
                  ? sku.ball_valve_kit
                  : null
              }
            />
          </section>
        </aside>
      </div>
    </div>
  );
}

function StructuredText({ text }: { text: string }) {
  return (
    <div className={styles.description}>
      <InstructionText
        text={text}
        parse={parseProductDescription}
        styles={{
          lead: styles.descLead,
          docTitle: styles.descDocTitle,
          section: styles.descSection,
          subsection: styles.descSubsection,
          list: styles.descList,
        }}
      />
    </div>
  );
}
