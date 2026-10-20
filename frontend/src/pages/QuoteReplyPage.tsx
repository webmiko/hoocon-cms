/**
 * /kp — client accepts a quote or asks for changes, without a cabinet login.
 * The token lives in the URL fragment so it is not sent to the server or
 * to analytics. Old emails still put it in the query; those keep working.
 */

import { useState, type FormEvent } from "react";

import { AccountApiError, accountApi, type QuoteReplyPreview } from "../account/api";
import styles from "../account/Account.module.css";
import { Seo } from "../components/Seo";
import { useAsync } from "../hooks/useAsync";

function replyLink(): { token: string; action: "accept" | "revise" } {
  if (typeof window === "undefined") {
    return { token: "", action: "accept" };
  }
  const hashed = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const query = new URLSearchParams(window.location.search);
  const token = hashed.get("t") || query.get("t") || "";
  const action = (hashed.get("action") || query.get("action")) === "revise" ? "revise" : "accept";
  return { token, action };
}

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  const [year, month, day] = iso.split("-");
  if (!year || !month || !day) return iso;
  return `${day}.${month}.${year}`;
}

export default function QuoteReplyPage() {
  const { token, action } = replyLink();
  const { data, loading, error } = useAsync(
    () =>
      token
        ? accountApi.quoteReply(token)
        : Promise.reject(new AccountApiError(404, "Ссылка недействительна.")),
    token,
  );
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<QuoteReplyPreview | null>(null);
  const [notice, setNotice] = useState("");
  const [noticeIsError, setNoticeIsError] = useState(false);

  const quote = done ?? data;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token || !quote) return;
    setBusy(true);
    setNotice("");
    setNoticeIsError(false);
    try {
      const next = await accountApi.submitQuoteReply(token, action, comment);
      setDone(next);
      setNotice(action === "accept" ? "Предложение согласовано." : "Правки отправлены менеджеру.");
    } catch (err) {
      setNoticeIsError(true);
      setNotice(err instanceof AccountApiError ? err.detail : "Не удалось отправить.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.page}>
      <Seo
        title="Коммерческое предложение"
        description="Ответ на коммерческое предложение Hoocon."
        noindex
      />
      <h1 className={styles.title}>Коммерческое предложение</h1>
      {loading && <p className={styles.muted}>Загрузка…</p>}
      {error && !quote && (
        <p className={styles.error}>
          {error instanceof AccountApiError ? error.detail : "Ссылка недействительна."}
        </p>
      )}
      {quote && (
        <form className={styles.form} onSubmit={(event) => void submit(event)}>
          <p className={styles.intro}>
            {quote.number}
            {quote.valid_until ? ` · действует до ${fmtDate(quote.valid_until)}` : ""}
            {quote.manager_name ? ` · ${quote.manager_name}` : ""}
            {quote.manager_phone ? `, ${quote.manager_phone}` : ""}
          </p>
          <p className={styles.muted}>Статус: {quote.status_label}</p>
          {quote.expired && (
            <p className={styles.error}>Срок предложения истёк. Напишите менеджеру.</p>
          )}
          {action === "revise" && quote.status !== "rejected" && (
            <label className={styles.field}>
              <span className={styles.label}>Что поправить</span>
              <textarea
                className={styles.input}
                rows={5}
                value={comment}
                onChange={(event) => setComment(event.target.value)}
                required
              />
            </label>
          )}
          {action === "accept" && quote.can_accept && (
            <button className={styles.button} type="submit" disabled={busy}>
              Согласовать
            </button>
          )}
          {action === "revise" && (quote.status === "sent" || quote.status === "accepted") && (
            <button className={styles.button} type="submit" disabled={busy}>
              Отправить правки
            </button>
          )}
          {notice && <p className={noticeIsError ? styles.error : styles.success}>{notice}</p>}
        </form>
      )}
    </div>
  );
}
