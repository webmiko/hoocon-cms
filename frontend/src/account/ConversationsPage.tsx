/**
 * /account/conversations — linked support-chat threads (ЛК-4).
 */

import { useAsync } from "../hooks/useAsync";
import styles from "./Account.module.css";
import { accountApi } from "./api";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function ConversationsPage() {
  const { data, loading, error } = useAsync(() => accountApi.conversations());

  if (loading) return <p className={styles.muted}>Загрузка…</p>;
  if (error) return <p className={styles.error}>Не удалось загрузить диалоги.</p>;

  const convs = data ?? [];
  return (
    <section>
      {convs.length === 0 ? (
        <p className={styles.muted}>Диалогов пока нет.</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Диалог</th>
              <th>Канал</th>
              <th>Статус</th>
              <th>Обновлён</th>
            </tr>
          </thead>
          <tbody>
            {convs.map((c) => (
              <tr key={c.id}>
                <td>{c.subject}</td>
                <td>{c.channel_label}</td>
                <td>
                  <span className={styles.badge}>{c.status_label}</span>
                </td>
                <td>{fmtDate(c.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
