/**
 * /account/leads — own leads with repeat-request action (ЛК-2).
 */

import { useState } from "react";
import { Link } from "react-router-dom";

import { useAsync } from "../hooks/useAsync";
import styles from "./Account.module.css";
import { accountApi, AccountApiError, type AccountLead } from "./api";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export default function LeadsPage() {
  const { data, loading, error } = useAsync(() => accountApi.leads());
  const [busyId, setBusyId] = useState<number | null>(null);
  const [notice, setNotice] = useState("");

  if (loading) return <p className={styles.muted}>Загрузка…</p>;
  if (error) return <p className={styles.error}>Не удалось загрузить заявки.</p>;

  const leads: AccountLead[] = Array.isArray(data)
    ? data
    : ((data?.results as AccountLead[] | undefined) ?? []);

  async function repeat(id: number) {
    setBusyId(id);
    setNotice("");
    try {
      const lead = await accountApi.repeatLead(id);
      setNotice(`Создана заявка #${lead.id} — менеджер свяжется с вами.`);
    } catch (err) {
      setNotice(err instanceof AccountApiError ? err.detail : "Не удалось повторить заявку.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section>
      <div className={styles.actions}>
        <Link className={styles.button} to="/rfq">
          Новая заявка
        </Link>
      </div>
      {notice && <p className={styles.success}>{notice}</p>}
      {leads.length === 0 ? (
        <p className={styles.muted}>Заявок пока нет.</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>#</th>
              <th>Тип</th>
              <th>Статус</th>
              <th>Позиций</th>
              <th>Дата</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {leads.map((lead) => (
              <tr key={lead.id}>
                <td>{lead.id}</td>
                <td>{lead.type_label}</td>
                <td>
                  <span className={lead.status === "done" ? styles.badge : styles.badgeAccent}>
                    {lead.status_label}
                  </span>
                </td>
                <td>{lead.items.length}</td>
                <td>{fmtDate(lead.created_at)}</td>
                <td>
                  <button
                    type="button"
                    className={styles.buttonGhost}
                    disabled={busyId === lead.id}
                    onClick={() => void repeat(lead.id)}
                  >
                    Повторить
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
