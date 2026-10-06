/**
 * CabinetOffer — post-lead upsell shown on the success screen.
 *
 * One-step onboarding: ``otpStart`` auto-creates the account for a new
 * email, and the just-submitted lead is already linked to the CRM client
 * by that email — after ``otpVerify`` it appears in ``/account/leads``.
 * For already-authenticated visitors the block degrades to a deep link.
 */

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import account from "./Account.module.css";
import { accountApi, AccountApiError } from "./api";
import { useAccountAuth } from "./AuthContext";
import styles from "./CabinetOffer.module.css";

interface CabinetOfferProps {
  /** Email captured from the submitted lead form (always required there). */
  email: string;
}

export function CabinetOffer({ email }: CabinetOfferProps) {
  const navigate = useNavigate();
  const { session, loading, refresh } = useAccountAuth();
  const [challengeId, setChallengeId] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  // Stamped on mount (not during render) for the server-side min-fill check.
  const formStartTs = useRef(0);
  useEffect(() => {
    formStartTs.current = Date.now() / 1000;
  }, []);

  if (loading || dismissed || !email) {
    return null;
  }

  if (session) {
    return (
      <section className={styles.offer}>
        <h3 className={styles.title}>Заявка уже в вашем кабинете</h3>
        <p className={styles.hint}>
          Статус обработки, КП и документы — в разделе «Заявки».
        </p>
        <Link className={account.button} to="/account/leads">
          Открыть кабинет
        </Link>
      </section>
    );
  }

  async function onStart(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await accountApi.otpStart(email, formStartTs.current);
      setChallengeId(res.challenge_id);
    } catch (err) {
      setError(
        err instanceof AccountApiError ? err.detail : "Не удалось отправить код.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function onVerify(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await accountApi.otpVerify(challengeId, code.trim());
      await refresh();
      navigate("/account/leads", { replace: true });
    } catch (err) {
      setError(err instanceof AccountApiError ? err.detail : "Неверный код.");
    } finally {
      setBusy(false);
    }
  }

  if (challengeId) {
    return (
      <form className={styles.offer} onSubmit={onVerify}>
        <p className={styles.hint}>
          Код отправлен на <strong>{email}</strong> — введите 6 цифр из письма.
        </p>
        <label className={account.field}>
          <span className={account.label}>Код из письма</span>
          <input
            className={account.input}
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </label>
        {error && (
          <p className={account.error} role="alert">
            {error}
          </p>
        )}
        <div className={styles.row}>
          <button className={account.button} type="submit" disabled={busy}>
            Войти в кабинет
          </button>
          <button
            type="button"
            className={styles.dismiss}
            disabled={busy}
            onClick={async () => {
              setError("");
              try {
                await accountApi.otpResend(challengeId);
              } catch (err) {
                setError(
                  err instanceof AccountApiError
                    ? err.detail
                    : "Повторите позже.",
                );
              }
            }}
          >
            Отправить ещё раз
          </button>
        </div>
      </form>
    );
  }

  return (
    <form className={styles.offer} onSubmit={onStart}>
      <h3 className={styles.title}>Следите за заявкой в личном кабинете</h3>
      <ul className={styles.benefits}>
        <li>Статус заявки и готовое КП с PDF — сразу, не дожидаясь письма</li>
        <li>История заявок, заказов и документов вашей компании</li>
        <li>Повторная заявка в один клик и подбор аналогов</li>
      </ul>
      <p className={styles.hint}>
        Без пароля — пришлём код для входа на <strong>{email}</strong>
      </p>
      {error && (
        <p className={account.error} role="alert">
          {error}
        </p>
      )}
      <div className={styles.row}>
        <button className={account.button} type="submit" disabled={busy}>
          Создать кабинет
        </button>
        <button
          type="button"
          className={styles.dismiss}
          onClick={() => setDismissed(true)}
        >
          Не сейчас
        </button>
      </div>
    </form>
  );
}
