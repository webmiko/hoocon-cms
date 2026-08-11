import { FormEvent, useEffect, useId, useRef, useState } from "react";

import { api } from "../api/client";
import styles from "./SupportWidget.module.css";

type ChatMessage = {
  id: number;
  direction: string;
  body: string;
  outside_hours: boolean;
  created_at: string;
};

type ChannelLink = { channel: string; label: string; deep_link: string };

/**
 * Floating support chat (web channel) with Telegram deep link.
 * Polls for staff replies; respects outside-hours banner from API.
 */
export function SupportWidget() {
  const titleId = useId();
  const [open, setOpen] = useState(false);
  const [started, setStarted] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [isOpenNow, setIsOpenNow] = useState(true);
  const [outsideHint, setOutsideHint] = useState("");
  const [channels, setChannels] = useState<ChannelLink[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const lastIdRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [schedule, ch] = await Promise.all([
          api.supportSchedule(),
          api.supportChannels(),
        ]);
        if (cancelled) return;
        setIsOpenNow(schedule.is_open_now);
        setOutsideHint(schedule.auto_reply_outside_hours || "");
        setChannels(ch.channels);
      } catch {
        /* widget stays usable; schedule optional */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!open || !started) return;
    const tick = async () => {
      try {
        const after = lastIdRef.current > 0 ? lastIdRef.current : undefined;
        const data = await api.supportMessages(after);
        if (!data.messages.length) return;
        setMessages((prev) => {
          const seen = new Set(prev.map((m) => m.id));
          const merged = [...prev];
          for (const m of data.messages) {
            if (!seen.has(m.id)) merged.push(m);
          }
          return merged;
        });
        lastIdRef.current = Math.max(
          lastIdRef.current,
          ...data.messages.map((m) => m.id),
        );
      } catch {
        /* ignore poll errors */
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 4000);
    return () => window.clearInterval(id);
  }, [open, started]);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, open]);

  async function ensureStarted() {
    if (started) return;
    await api.fetchCsrfToken();
    await api.supportStartConversation({
      display_name: name.trim() || undefined,
      contact_email: email.trim() || undefined,
    });
    setStarted(true);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const body = draft.trim();
    if (!body || busy) return;
    setBusy(true);
    setError("");
    try {
      await ensureStarted();
      const result = await api.supportSendMessage(body);
      const next = [result.message];
      if (result.auto_reply) next.push(result.auto_reply);
      setMessages((prev) => [...prev, ...next]);
      lastIdRef.current = Math.max(
        lastIdRef.current,
        ...next.map((m) => m.id),
      );
      setDraft("");
      if (result.message.outside_hours) setIsOpenNow(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отправить");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.root}>
      {open ? (
        <section
          className={styles.panel}
          aria-labelledby={titleId}
          role="dialog"
          aria-modal="false"
        >
          <header className={styles.header}>
            <div>
              <h2 id={titleId} className={styles.title}>
                Поддержка Hoocon
              </h2>
              <p className={styles.status}>
                {isOpenNow ? "Сейчас на связи" : "Вне рабочего времени"}
              </p>
            </div>
            <button
              type="button"
              className={styles.close}
              aria-label="Закрыть чат"
              onClick={() => setOpen(false)}
            >
              ×
            </button>
          </header>

          {!isOpenNow && outsideHint ? (
            <p className={styles.banner}>{outsideHint}</p>
          ) : null}

          <div className={styles.meta}>
            <label className={styles.field}>
              <span>Имя</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="name"
                maxLength={200}
              />
            </label>
            <label className={styles.field}>
              <span>Email</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                maxLength={254}
              />
            </label>
          </div>

          <div className={styles.messages} ref={listRef}>
            {messages.length === 0 ? (
              <p className={styles.empty}>
                Напишите вопрос по приводам, арматуре или КП — ответим в этом
                окне.
              </p>
            ) : (
              messages.map((m) => (
                <div
                  key={m.id}
                  className={
                    m.direction === "inbound" ? styles.bubbleOut : styles.bubbleIn
                  }
                >
                  {m.body}
                </div>
              ))
            )}
          </div>

          {channels.length > 0 ? (
            <div className={styles.channels}>
              <span>Или напишите в</span>
              {channels.map((ch) => (
                <a
                  key={ch.channel}
                  href={ch.deep_link}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {ch.label}
                </a>
              ))}
            </div>
          ) : null}

          <form className={styles.composer} onSubmit={(e) => void onSubmit(e)}>
            <label className={styles.srOnly} htmlFor={`${titleId}-draft`}>
              Сообщение
            </label>
            <textarea
              id={`${titleId}-draft`}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={2}
              maxLength={4000}
              placeholder="Ваше сообщение…"
              required
            />
            {/* honeypot unused in UI — bots that fill `website` via API only */}
            <button type="submit" disabled={busy || !draft.trim()}>
              Отправить
            </button>
          </form>
          {error ? <p className={styles.error}>{error}</p> : null}
        </section>
      ) : null}

      <button
        type="button"
        className={styles.fab}
        aria-expanded={open}
        aria-controls={open ? undefined : undefined}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "Закрыть" : "Чат"}
      </button>
    </div>
  );
}
