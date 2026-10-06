/**
 * /register — client cabinet registration (mode A: email + password).
 *
 * Honeypot field ``website`` is invisible to humans; ``form_start_ts``
 * marks render time for the server-side min-fill check.
 */

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Seo } from "../components/Seo";
import styles from "./Account.module.css";
import { accountApi, AccountApiError } from "./api";
import { useAccountAuth } from "./AuthContext";

export default function RegisterPage() {
  const navigate = useNavigate();
  const { refresh } = useAccountAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [website, setWebsite] = useState(""); // honeypot trap
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Stamped on mount (not during render) for the server-side min-fill check.
  const formStartTs = useRef(0);
  useEffect(() => {
    formStartTs.current = Date.now() / 1000;
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (password !== password2) {
      setError("Пароли не совпадают.");
      return;
    }
    setBusy(true);
    try {
      await accountApi.register({
        email: email.trim(),
        password,
        name: name.trim(),
        phone: phone.trim(),
        form_start_ts: formStartTs.current,
        website,
      });
      await refresh();
      navigate("/account", { replace: true });
    } catch (err) {
      setError(err instanceof AccountApiError ? err.detail : "Не удалось зарегистрироваться.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.page}>
      <Seo title="Регистрация" description="Регистрация личного кабинета клиента Hoocon." noindex />
      <h1 className={styles.title}>Регистрация</h1>
      <p className={styles.intro}>
        Кабинет привяжется к вашей почте — заявки и документы компании появятся автоматически.
      </p>

      <form className={styles.form} onSubmit={onSubmit}>
        <div className={styles.honeypot} aria-hidden="true">
          <label>
            Не заполняйте
            <input
              type="text"
              name="website"
              tabIndex={-1}
              autoComplete="off"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
            />
          </label>
        </div>
        <label className={styles.field}>
          <span className={styles.label}>Эл. почта</span>
          <input
            className={styles.input}
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>Имя / компания</span>
          <input
            className={styles.input}
            type="text"
            autoComplete="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>Телефон</span>
          <input
            className={styles.input}
            type="tel"
            autoComplete="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>Пароль (минимум 8 символов)</span>
          <input
            className={styles.input}
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>Пароль ещё раз</span>
          <input
            className={styles.input}
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={password2}
            onChange={(e) => setPassword2(e.target.value)}
          />
        </label>
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
        <button className={styles.button} type="submit" disabled={busy}>
          Зарегистрироваться
        </button>
      </form>

      <p className={styles.muted}>
        Уже есть аккаунт? <Link to="/login">Войти</Link>
      </p>
    </div>
  );
}
