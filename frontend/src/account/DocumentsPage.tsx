/**
 * /account/documents — client files with owner-scoped download + ZIP (ЛК-7/8).
 */

import { useAsync } from "../hooks/useAsync";
import styles from "./Account.module.css";
import { accountApi } from "./api";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU");
}

export default function DocumentsPage() {
  const { data, loading, error } = useAsync(() => accountApi.documents());

  if (loading) return <p className={styles.muted}>Загрузка…</p>;
  if (error) return <p className={styles.error}>Не удалось загрузить документы.</p>;

  const docs = data ?? [];
  return (
    <section>
      {docs.length > 0 && (
        <div className={styles.actions}>
          <a className={styles.buttonGhost} href={accountApi.documentsZipUrl()}>
            Скачать всё ZIP
          </a>
        </div>
      )}
      {docs.length === 0 ? (
        <p className={styles.muted}>Документов пока нет.</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Название</th>
              <th>Тип</th>
              <th>ЭДО</th>
              <th>Дата</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {docs.map((doc) => (
              <tr key={doc.id}>
                <td>{doc.title}</td>
                <td>{doc.kind_label}</td>
                <td>{doc.edo_status_label || "—"}</td>
                <td>{fmtDate(doc.created_at)}</td>
                <td>
                  <a className={styles.buttonGhost} href={accountApi.documentDownloadUrl(doc.id)}>
                    Скачать
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
