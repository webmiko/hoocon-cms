import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { LeadForm } from "../components/LeadForm";
import styles from "./SkuDetailPage.module.css";

/** File item from SKU detail (drf-spectacular types files as unknown[]). */
interface SkuFile {
  id: number;
  title: string;
  file: string;
  file_type: string;
  sort_order: number;
}

/**
 * SKU detail page (PDP): ТТХ table, PDF files, CTA «Запросить КП».
 *
 * Spec: ПЛАН §6 Iter 4; docs/readiness-backend-ux.md §2.3 (M2 — карточка SKU).
 * CTA opens a lead form (RFQ) pre-filled with the SKU context.
 */
export function SkuDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const { data: sku, loading, error } = useAsync(
    () => api.skuDetail(slug!),
    [slug],
  );

  if (loading) {
    return <p className={styles.status}>Загрузка…</p>;
  }

  if (error || !sku) {
    return (
      <div className={styles.notFound}>
        <h1>Товар не найден</h1>
        <p>Возможно, страница была перемещена или удалена.</p>
        <Link to="/catalog" className={styles.link}>
          ← Вернуться в каталог
        </Link>
      </div>
    );
  }

  // Cast files to typed shape (schema types them as unknown[]).
  const files: SkuFile[] = (sku.files ?? []) as unknown[] as SkuFile[];

  return (
    <div className={styles.detail}>
      {/* Breadcrumbs */}
      <nav className={styles.breadcrumbs} aria-label="Навигация">
        <Link to="/catalog">Каталог</Link>
        {sku.category_slug && (
          <>
            <span className={styles.crumbSep}>/</span>
            <Link to={`/catalog?category=${encodeURIComponent(sku.category_slug)}`}>
              {sku.category_slug}
            </Link>
          </>
        )}
        <span className={styles.crumbSep}>/</span>
        <span className={styles.crumbCurrent}>{sku.name}</span>
      </nav>

      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>{sku.name}</h1>
          <p className={styles.skuCode}>Артикул: {sku.sku_code}</p>
          {sku.analog_belimo_code && (
            <p className={styles.analog}>
              Аналог Belimo: <strong>{sku.analog_belimo_code}</strong>
            </p>
          )}
        </div>
        <div className={styles.priceBlock}>
          {"price" in sku && sku.price ? (
            <p className={styles.price}>{sku.price} ₽</p>
          ) : sku.price_on_request ? (
            <p className={styles.priceOnRequest}>Цена по запросу</p>
          ) : null}
        </div>
      </div>

      {sku.description && (
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Описание</h2>
          <div className={styles.description}>{sku.description}</div>
        </section>
      )}

      {/* ТТХ table */}
      {sku.attributes && sku.attributes.length > 0 && (
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Технические характеристики</h2>
          <table className={styles.specTable}>
            <tbody>
              {sku.attributes.map((attr) => (
                <tr key={attr.slug}>
                  <th className={styles.specName}>{attr.name}</th>
                  <td className={styles.specValue}>
                    {attr.value}
                    {attr.unit && <span className={styles.specUnit}> {attr.unit}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Files (PDF) */}
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

      {/* CTA: Request a quote (RFQ) */}
      <section className={styles.ctaSection}>
        <h2 className={styles.ctaTitle}>Запросить коммерческое предложение</h2>
        <p className={styles.ctaText}>
          Отправьте заявку — менеджер подготовит КП на {sku.name} (арт. {sku.sku_code})
          и свяжется с вами.
        </p>
        <LeadForm leadType="rfq" skuSlug={sku.slug} skuName={sku.name} />
      </section>
    </div>
  );
}
