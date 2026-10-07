/**
 * /login — client cabinet sign-in: password (mode A) or email OTP (mode B).
 *
 * OTP flow: start → challenge_id → code → verify. Session lands in the
 * HttpOnly cookie — nothing is stored client-side.
 */

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Seo } from "../components/Seo";
import styles from "./Account.module.css";
import { accountApi, AccountApiError } from "./api";
import { useAccountAuth } from "./AuthContext";

type Mode = "password" | "otp";

export default function LoginPage() {
  const navigate = useNavigate();
  const { refresh } = useAccountAuth();
  const [mode, setMode] = useState<Mode>("password");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [challengeId, setChallengeId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Stamped on mount (not during render) for the server-side min-fill check.
  const formStartTs = useRef(0);
  useEffect(() => {
    formStartTs.current = Date.now() / 1000;
  }, []);

  async function finish() {
    await refresh();
    navigate("/account", { replace: true });
  }

  async function onPasswordSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await accountApi.login(email.trim(), password);
      await finish();
    } catch (err) {
      setError(err instanceof AccountApiError ? err.detail : "Не удалось войти.");
    } finally {
      setBusy(false);
    }
  }

  async function onOtpStart(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await accountApi.otpStart(email.trim(), formStartTs.current);
      setChallengeId(res.challenge_id);
    } catch (err) {
      setError(err instanceof AccountApiError ? err.detail : "Не удалось отправить код.");
    } finally {
      setBusy(false);
    }
  }

  async function onOtpVerify(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await accountApi.otpVerify(challengeId, code.trim());
      await finish();
    } catch (err) {
      setError(err instanceof AccountApiError ? err.detail : "Неверный код.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.page}>
      <Seo
        title="Вход в личный кабинет"
        description="Вход в личный кабинет клиента Hoocon."
        noindex
      />
      <h1 className={styles.title}>Личный кабинет</h1>
      <p className={styles.intro}>Заявки, КП, заказы и документы вашей компании — в одном месте.</p>

      <ul className={styles.tabs}>
        <li className={styles.tab}>
          <a
            href="#password"
            aria-current={mode === "password" ? "page" : undefined}
            onClick={(e) => {
              e.preventDefault();
              setMode("password");
              setError("");
            }}
          >
            По паролю
          </a>
        </li>
        <li className={styles.tab}>
          <a
            href="#otp"
            aria-current={mode === "otp" ? "page" : undefined}
            onClick={(e) => {
              e.preventDefault();
              setMode("otp");
              setError("");
            }}
          >
            По коду из письма
          </a>
        </li>
      </ul>

      {mode === "password" ? (
        <form className={styles.form} onSubmit={onPasswordSubmit}>
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
            <span className={styles.label}>Пароль</span>
            <input
              className={styles.input}
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {error && (
            <p className={styles.error} role="alert">
              {error}
            </p>
          )}
          <button className={styles.button} type="submit" disabled={busy}>
            Войти
          </button>
        </form>
      ) : challengeId ? (
        <form className={styles.form} onSubmit={onOtpVerify}>
          <p className={styles.muted}>Код отправлен на {email} — введите 6 цифр.</p>
          <label className={styles.field}>
            <span className={styles.label}>Код из письма</span>
            <input
              className={styles.input}
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          </label>
          {error && (
            <p className={styles.error} role="alert">
              {error}
            </p>
          )}
          <div className={styles.actions}>
            <button className={styles.button} type="submit" disabled={busy}>
              Войти
            </button>
            <button
              type="button"
              className={styles.buttonGhost}
              disabled={busy}
              onClick={async () => {
                setError("");
                try {
                  await accountApi.otpResend(challengeId);
                } catch (err) {
                  setError(err instanceof AccountApiError ? err.detail : "Повторите позже.");
                }
              }}
            >
              Отправить ещё раз
            </button>
          </div>
        </form>
      ) : (
        <form className={styles.form} onSubmit={onOtpStart}>
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
          {error && (
            <p className={styles.error} role="alert">
              {error}
            </p>
          )}
          <button className={styles.button} type="submit" disabled={busy}>
            Получить код
          </button>
        </form>
      )}

      <p className={styles.muted}>
        Нет аккаунта? <Link to="/register">Регистрация</Link> — для клиентов и партнёров Hoocon.
      </p>
    </div>
  );
}
