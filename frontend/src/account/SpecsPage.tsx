/**
 * /account/specs — named spec templates: list, create, push to RFQ (ЛК-5).
 */

import { useState, type FormEvent } from "react";

import { useAsync } from "../hooks/useAsync";
import styles from "./Account.module.css";
import { accountApi, AccountApiError, type SpecList } from "./api";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU");
}

export default function SpecsPage() {
  const { data, loading, error } = useAsync(() => accountApi.specs());
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [lines, setLines] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  // Refresh via a second async read (simple remount of data).
  void refreshKey;
  const refetch = () => setRefreshKey((k) => k + 1);

  if (loading) return <p className={styles.muted}>Загрузка…</p>;
  if (error) return <p className={styles.error}>Не удалось загрузить спецификации.</p>;

  const specs: SpecList[] = data ?? [];

  async function createSpec(e: FormEvent) {
    e.preventDefault();
    setNotice("");
    setBusy(true);
    const items = lines
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map((l) => {
        const [code, qty] = l.split(/[;\t,]/).map((p) => p.trim());
        return { sku_code: code, quantity: Math.max(parseInt(qty ?? "1", 10) || 1, 1) };
      });
    try {
      await accountApi.saveSpec({ name: name.trim(), note: note.trim(), items });
      setName("");
      setNote("");
      setLines("");
      setShowForm(false);
      setNotice("Спецификация сохранена.");
      refetch();
      window.location.reload();
    } catch (err) {
      setNotice(err instanceof AccountApiError ? err.detail : "Не удалось сохранить.");
    } finally {
      setBusy(false);
    }
  }

  async function toLead(id: number) {
    setBusy(true);
    setNotice("");
    try {
      const lead = await accountApi.specToLead(id);
      setNotice(`Создана заявка #${lead.id} из спецификации.`);
    } catch (err) {
      setNotice(err instanceof AccountApiError ? err.detail : "Не удалось создать заявку.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    setBusy(true);
    try {
      await accountApi.deleteSpec(id);
      window.location.reload();
    } catch {
      setNotice("Не удалось удалить спецификацию.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <div className={styles.actions}>
        <button type="button" className={styles.button} onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Скрыть форму" : "Новая спецификация"}
        </button>
      </div>
      {notice && <p className={styles.success}>{notice}</p>}

      {showForm && (
        <form className={styles.form} onSubmit={createSpec}>
          <label className={styles.field}>
            <span className={styles.label}>Название</span>
            <input
              className={styles.input}
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>Заметка</span>
            <input
              className={styles.input}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>Позиции — по строке «артикул; количество»</span>
            <textarea
              className={styles.input}
              rows={6}
              placeholder={"HVA-5NM; 2\nBV215; 10"}
              value={lines}
              onChange={(e) => setLines(e.target.value)}
            />
          </label>
          <button className={styles.button} type="submit" disabled={busy}>
            Сохранить
          </button>
        </form>
      )}

      {specs.length === 0 && !showForm ? (
        <p className={styles.muted}>Спецификаций пока нет.</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Название</th>
              <th>Позиций</th>
              <th>Обновлена</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {specs.map((spec) => (
              <tr key={spec.id}>
                <td>
                  {spec.name}
                  {spec.note ? <div className={styles.muted}>{spec.note}</div> : null}
                </td>
                <td>{spec.items.length}</td>
                <td>{fmtDate(spec.updated_at)}</td>
                <td>
                  <div className={styles.actions}>
                    <button
                      type="button"
                      className={styles.buttonGhost}
                      disabled={busy}
                      onClick={() => void toLead(spec.id)}
                    >
                      В заявку
                    </button>
                    <button
                      type="button"
                      className={styles.buttonGhost}
                      disabled={busy}
                      onClick={() => void remove(spec.id)}
                    >
                      Удалить
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
