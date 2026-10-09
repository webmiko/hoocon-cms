/**
 * /register — client cabinet registration (mode A: email + password).
 *
 * Two steps: the form emails a code, the account is created only after
 * the code is confirmed — the cabinet shows CRM data matched by email.
 *
 * Honeypot field ``website`` is invisible to humans; ``form_start_ts``
 * marks render time for the server-side min-fill check.
 */

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { PdnConsentCheckbox } from "../components/PdnConsentCheckbox";
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
  const [challengeId, setChallengeId] = useState("");
  const [emailMasked, setEmailMasked] = useState("");
  const [code, setCode] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [pdnConsent, setPdnConsent] = useState(false);
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
      const challenge = await accountApi.register({
        email: email.trim(),
        password,
        name: name.trim(),
        phone: phone.trim(),
        form_start_ts: formStartTs.current,
        website,
        pdn_consent: pdnConsent,
      });
      setChallengeId(challenge.challenge_id);
      setEmailMasked(challenge.email_masked);
    } catch (err) {
      setError(err instanceof AccountApiError ? err.detail : "Не удалось зарегистрироваться.");
    } finally {
      setBusy(false);
    }
  }

  async function onVerify(e: FormEvent) {
    e.preventDefault();
    setError("");
    setNotice("");
    setBusy(true);
    try {
      await accountApi.otpVerify(challengeId, code.trim());
      await refresh();
      navigate("/account", { replace: true });
    } catch (err) {
      setError(err instanceof AccountApiError ? err.detail : "Неверный код.");
    } finally {
      setBusy(false);
    }
  }

  async function onResend() {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      await accountApi.otpResend(challengeId);
      setNotice("Код отправлен ещё раз.");
    } catch (err) {
      setError(err instanceof AccountApiError ? err.detail : "Повторите позже.");
    } finally {
      setBusy(false);
    }
  }

  if (challengeId) {
    return (
      <div className={styles.page}>
        <Seo title="Подтверждение почты" description="Подтверждение почты личного кабинета Hoocon." noindex />
        <h1 className={styles.title}>Подтвердите почту</h1>
        <p className={styles.intro}>
          Мы отправили код на {emailMasked}. Кабинет появится после ввода кода — так мы проверяем, что почта ваша.
        </p>
        <form className={styles.form} onSubmit={onVerify}>
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
          {notice && <p className={styles.muted}>{notice}</p>}
          {error && (
            <p className={styles.error} role="alert">
              {error}
            </p>
          )}
          <div className={styles.actions}>
            <button className={styles.button} type="submit" disabled={busy}>
              Подтвердить
            </button>
            <button type="button" className={styles.buttonGhost} disabled={busy} onClick={onResend}>
              Отправить ещё раз
            </button>
          </div>
        </form>
      </div>
    );
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
        <PdnConsentCheckbox checked={pdnConsent} onChange={setPdnConsent} />
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
        <button className={styles.button} type="submit" disabled={busy || !pdnConsent}>
          Зарегистрироваться
        </button>
      </form>

      <p className={styles.muted}>
        Уже есть аккаунт? <Link to="/login">Войти</Link>
      </p>
    </div>
  );
}
