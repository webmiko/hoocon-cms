/**
 * /account/quotes — issued quotes with PDF download (ЛК-3).
 */

import { useAsync } from "../hooks/useAsync";
import styles from "./Account.module.css";
import { accountApi } from "./api";

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("ru-RU");
}

export default function QuotesPage() {
  const { data, loading, error } = useAsync(() => accountApi.quotes());

  if (loading) return <p className={styles.muted}>Загрузка…</p>;
  if (error) return <p className={styles.error}>Не удалось загрузить КП.</p>;

  const quotes = data ?? [];
  return (
    <section>
      {quotes.length === 0 ? (
        <p className={styles.muted}>Выданных КП пока нет.</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Номер</th>
              <th>Статус</th>
              <th>Сумма</th>
              <th>Выдано</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {quotes.map((q) => (
              <tr key={q.id}>
                <td>{q.number}</td>
                <td>
                  <span className={styles.badgeAccent}>{q.status_label}</span>
                </td>
                <td>{q.total_amount ? `${q.total_amount} ₽` : "—"}</td>
                <td>{fmtDate(q.sent_at)}</td>
                <td>
                  <a
                    className={styles.buttonGhost}
                    href={accountApi.quotePdfUrl(q.id)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    PDF
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
