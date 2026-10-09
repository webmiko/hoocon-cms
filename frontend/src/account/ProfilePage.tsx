/**
 * /account/profile — editable profile + linked company details (ЛК-1/5).
 */

import { useState, type FormEvent } from "react";

import { useAsync } from "../hooks/useAsync";
import styles from "./Account.module.css";
import { accountApi, AccountApiError } from "./api";
import { useAccountAuth } from "./AuthContext";

export default function ProfilePage() {
  const { session, refresh } = useAccountAuth();
  const { data: company } = useAsync(() => accountApi.company());
  const [name, setName] = useState(session?.name ?? "");
  const [phone, setPhone] = useState(session?.phone ?? "");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setNotice("");
    try {
      await accountApi.updateProfile({ name: name.trim(), phone: phone.trim() });
      await refresh();
      setNotice("Профиль сохранён.");
    } catch (err) {
      setNotice(err instanceof AccountApiError ? err.detail : "Не удалось сохранить.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <form className={styles.form} onSubmit={submit}>
        <label className={styles.field}>
          <span className={styles.label}>Эл. почта (логин)</span>
          <input className={styles.input} value={session?.email ?? ""} disabled />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>Имя / контакт</span>
          <input className={styles.input} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>Телефон</span>
          <input
            className={styles.input}
            type="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </label>
        {notice && <p className={styles.success}>{notice}</p>}
        <button className={styles.button} type="submit" disabled={busy}>
          Сохранить
        </button>
      </form>

      {company && (company.name || company.inn) ? (
        <div className={styles.card} style={{ marginTop: "var(--space-lg)" }}>
          <h2 style={{ marginTop: 0 }}>Компания</h2>
          <p>
            <strong>{company.name}</strong>
            {company.inn ? ` · ИНН ${company.inn}` : ""}
          </p>
          {company.legal_address && <p className={styles.muted}>{company.legal_address}</p>}
          {company.members.length > 0 && (
            <p className={styles.muted}>Сотрудников: {company.members.length}</p>
          )}
          {!company.confirmed && (
            <p className={styles.muted}>
              Реквизиты появятся, когда менеджер подтвердит, что вы сотрудник компании.
            </p>
          )}
        </div>
      ) : null}
    </section>
  );
}
