/**
 * /account/rma — reclamations: list + submit form (ЛК-12).
 */

import { useState, type FormEvent } from "react";

import { useAsync } from "../hooks/useAsync";
import styles from "./Account.module.css";
import { accountApi, AccountApiError } from "./api";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU");
}

export default function RmaPage() {
  const { data, loading, error } = useAsync(() => accountApi.rmaCases());
  const { data: orders } = useAsync(() => accountApi.orders());
  const [showForm, setShowForm] = useState(false);
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [serial, setSerial] = useState("");
  const [orderId, setOrderId] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  if (loading) return <p className={styles.muted}>Загрузка…</p>;
  if (error) return <p className={styles.error}>Не удалось загрузить рекламации.</p>;

  const cases = data ?? [];

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setNotice("");
    try {
      await accountApi.createRma({
        subject: subject.trim(),
        description: description.trim(),
        serial_number: serial.trim(),
        order: orderId ? Number(orderId) : null,
        photo,
      });
      setNotice("Рекламация отправлена — менеджер свяжется с вами.");
      setSubject("");
      setDescription("");
      setSerial("");
      setOrderId("");
      setPhoto(null);
      setShowForm(false);
      window.location.reload();
    } catch (err) {
      setNotice(err instanceof AccountApiError ? err.detail : "Не удалось отправить.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <div className={styles.actions}>
        <button type="button" className={styles.button} onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Скрыть форму" : "Новая рекламация"}
        </button>
      </div>
      {notice && <p className={styles.success}>{notice}</p>}

      {showForm && (
        <form className={styles.form} onSubmit={submit}>
          <label className={styles.field}>
            <span className={styles.label}>Тема</span>
            <input
              className={styles.input}
              required
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>Серийный номер изделия</span>
            <input
              className={styles.input}
              value={serial}
              onChange={(e) => setSerial(e.target.value)}
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>Заказ (необязательно)</span>
            <select
              className={styles.input}
              value={orderId}
              onChange={(e) => setOrderId(e.target.value)}
            >
              <option value="">—</option>
              {(orders ?? []).map((o) => (
                <option key={o.id} value={o.id}>
                  {o.number}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.field}>
            <span className={styles.label}>Фото дефекта (необязательно)</span>
            <input
              className={styles.input}
              type="file"
              accept="image/*"
              onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>Описание проблемы</span>
            <textarea
              className={styles.input}
              rows={5}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          <button className={styles.button} type="submit" disabled={busy}>
            Отправить
          </button>
        </form>
      )}

      {cases.length === 0 && !showForm ? (
        <p className={styles.muted}>Рекламаций пока нет.</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>#</th>
              <th>Тема</th>
              <th>Серийный номер</th>
              <th>Статус</th>
              <th>Фото</th>
              <th>Дата</th>
            </tr>
          </thead>
          <tbody>
            {cases.map((c) => (
              <tr key={c.id}>
                <td>{c.id}</td>
                <td>{c.subject}</td>
                <td>{c.serial_number || "—"}</td>
                <td>
                  <span className={styles.badgeAccent}>{c.status_label}</span>
                </td>
                <td>
                  {c.has_photo ? (
                    <a href={accountApi.rmaPhotoUrl(c.id)} target="_blank" rel="noreferrer">
                      открыть
                    </a>
                  ) : (
                    "—"
                  )}
                </td>
                <td>{fmtDate(c.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
