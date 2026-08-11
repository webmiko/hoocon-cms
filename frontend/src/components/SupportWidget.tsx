import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { api } from "../api/client";
import {
  closeSupportChat,
  getSupportChatState,
  hideSupportChat,
  setSupportChatOpen,
  subscribeSupportChat,
} from "../utils/supportChatControl";
import {
  pushSupported,
  subscribeWebPush,
  subscribeWebPushStatusRu,
  syncExistingWebPush,
} from "../utils/webPush";
import styles from "./SupportWidget.module.css";

type ChatMessage = {
  id: number;
  direction: string;
  body: string;
  outside_hours: boolean;
  created_at: string;
  sender_name: string;
};

type ChannelLink = { channel: string; label: string; deep_link: string };

function mergeMessages(
  prev: ChatMessage[],
  incoming: ChatMessage[],
): ChatMessage[] {
  if (!incoming.length) return prev;
  const seen = new Set(prev.map((m) => m.id));
  const merged = [...prev];
  for (const m of incoming) {
    if (!seen.has(m.id)) merged.push(m);
  }
  return merged;
}

function maxMessageId(messages: ChatMessage[], fallback = 0): number {
  if (!messages.length) return fallback;
  return Math.max(fallback, ...messages.map((m) => m.id));
}

function formatMessageTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ChatIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d={
          "M4.5 4.75A2.75 2.75 0 0 1 7.25 2h9.5A2.75 2.75 0 0 1 19.5 4.75v8.5A2.75 " +
          "2.75 0 0 1 16.75 16H12.1l-3.72 3.1a.75.75 0 0 1-1.23-.57V16H7.25A2.75 " +
          "2.75 0 0 1 4.5 13.25v-8.5Z"
        }
      />
    </svg>
  );
}

function CloseIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        d="M7 7l10 10M17 7 7 17"
      />
    </svg>
  );
}

function SendIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d={
          "M3.4 11.2 19.1 3.7a1 1 0 0 1 1.4 1.1l-2.9 14.6a1 1 0 0 1-1.6.6l-4.7-3.5-2.4 " +
          "2.3a.75.75 0 0 1-1.3-.5v-3.7l11-8.4-13.2 5.9Z"
        }
      />
    </svg>
  );
}

/**
 * Floating support chat (web channel) with Telegram deep link.
 * Polls for staff replies; respects outside-hours banner from API.
 */
export function SupportWidget() {
  const titleId = useId();
  const initial = getSupportChatState();
  const [visible, setVisible] = useState(initial.visible);
  const [open, setOpen] = useState(initial.open);
  const [started, setStarted] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [contactsLocked, setContactsLocked] = useState(false);
  const [isOpenNow, setIsOpenNow] = useState(true);
  const [outsideHint, setOutsideHint] = useState("");
  const [channels, setChannels] = useState<ChannelLink[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pushStatus, setPushStatus] = useState("");
  const [pushEnabled, setPushEnabled] = useState(false);
  const [pushBusy, setPushBusy] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const lastIdRef = useRef(0);
  const resumeOnceRef = useRef(false);

  useEffect(
    () =>
      subscribeSupportChat((next) => {
        setVisible(next.visible);
        setOpen(next.open);
      }),
    [],
  );

  // Lift other fixed banners (marketing push) above the chat FAB.
  useEffect(() => {
    const root = document.documentElement;
    if (!visible || open) {
      root.style.setProperty("--support-chrome", "0px");
    } else {
      // FAB 3.25rem + gap under the banner.
      root.style.setProperty("--support-chrome", "4.25rem");
    }
    return () => {
      root.style.setProperty("--support-chrome", "0px");
    };
  }, [visible, open]);

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

  // On open: resume session + full history (PWA reload must see staff replies).
  useEffect(() => {
    if (!open) {
      resumeOnceRef.current = false;
      return;
    }
    if (resumeOnceRef.current) return;
    resumeOnceRef.current = true;
    let cancelled = false;
    void (async () => {
      try {
        await api.fetchCsrfToken();
        const startedConv = await api.supportStartConversation({});
        if (cancelled) return;
        setStarted(true);
        if (startedConv.display_name) {
          setName(startedConv.display_name);
        }
        if (startedConv.contact_email) {
          setEmail(startedConv.contact_email);
        }
        if (startedConv.display_name || startedConv.contact_email) {
          setContactsLocked(true);
        }
        const data = await api.supportMessages();
        if (cancelled) return;
        setMessages(data.messages);
        lastIdRef.current = maxMessageId(data.messages);
      } catch {
        /* first message path still works via ensureStarted */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (!open || !started) return;
    const tick = async () => {
      try {
        const after = lastIdRef.current > 0 ? lastIdRef.current : undefined;
        const data = await api.supportMessages(after);
        if (!data.messages.length) return;
        setMessages((prev) => mergeMessages(prev, data.messages));
        lastIdRef.current = maxMessageId(data.messages, lastIdRef.current);
      } catch {
        /* ignore transient poll errors (network); do not starve UI */
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 2500);
    return () => window.clearInterval(id);
  }, [open, started]);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, open]);

  // Mobile fullscreen chat: lock page scroll; track viewport changes.
  useEffect(() => {
    if (!open) return;
    const mq = window.matchMedia("(max-width: 720px)");
    const root = document.documentElement;
    let prevOverflow = root.style.overflow;

    function apply() {
      if (mq.matches) {
        prevOverflow = root.style.overflow;
        root.style.overflow = "hidden";
      } else {
        root.style.overflow = prevOverflow;
      }
    }
    apply();
    mq.addEventListener("change", apply);
    return () => {
      mq.removeEventListener("change", apply);
      root.style.overflow = prevOverflow;
    };
  }, [open]);

  // Escape closes the panel (fullscreen sheet / desktop card).
  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") closeSupportChat();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Re-bind support push only after explicit opt-in (never auto-OR topic_support).
  useEffect(() => {
    if (!open || !pushSupported()) return;
    let cancelled = false;
    void (async () => {
      let optedIn = false;
      try {
        optedIn = localStorage.getItem("hoocon-support-push-subscribed") === "1";
      } catch {
        /* private mode / blocked storage — treat as not opted in */
      }
      if (!optedIn) return;
      if (Notification.permission !== "granted") {
        try {
          localStorage.removeItem("hoocon-support-push-subscribed");
        } catch {
          /* ignore */
        }
        return;
      }
      const synced = await syncExistingWebPush({ topic_support: true });
      if (cancelled) return;
      if (synced?.ok) {
        setPushEnabled(true);
        setPushStatus("Уведомления об ответах включены");
      } else {
        try {
          localStorage.removeItem("hoocon-support-push-subscribed");
        } catch {
          /* ignore */
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  async function enablePush() {
    setPushStatus("");
    setPushBusy(true);
    try {
      const result = await subscribeWebPush({ topic_support: true });
      if (result.ok) {
        try {
          localStorage.setItem("hoocon-support-push-subscribed", "1");
        } catch {
          /* ignore */
        }
        setPushEnabled(true);
        setPushStatus("Уведомления об ответах включены");
      } else {
        setPushStatus(subscribeWebPushStatusRu(result));
      }
    } catch {
      setPushStatus("Не удалось включить уведомления");
    } finally {
      setPushBusy(false);
    }
  }

  async function syncContacts(force = false) {
    const displayName = name.trim();
    const contactEmail = email.trim();
    if (!force && !displayName && !contactEmail) {
      if (!started) {
        await api.fetchCsrfToken();
        await api.supportStartConversation({});
        setStarted(true);
      }
      return;
    }
    await api.fetchCsrfToken();
    const conv = await api.supportStartConversation({
      display_name: displayName || undefined,
      contact_email: contactEmail || undefined,
    });
    setStarted(true);
    if (conv.display_name) setName(conv.display_name);
    if (conv.contact_email) setEmail(conv.contact_email);
    const lockedName = (conv.display_name || displayName).trim();
    if (conv.display_name || conv.contact_email || displayName || contactEmail) {
      setContactsLocked(true);
    }
    if (lockedName) {
      setMessages((prev) =>
        prev.map((m) =>
          m.direction === "inbound" ? { ...m, sender_name: lockedName } : m,
        ),
      );
    }
  }

  async function ensureStarted() {
    if (started && contactsLocked) return;
    await syncContacts();
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
      setMessages((prev) => mergeMessages(prev, next));
      lastIdRef.current = maxMessageId(next, lastIdRef.current);
      setDraft("");
      if (result.message.outside_hours) setIsOpenNow(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отправить");
    } finally {
      setBusy(false);
    }
  }

  async function onSaveContacts(event: FormEvent) {
    event.preventDefault();
    if (busy || (!name.trim() && !email.trim())) return;
    setBusy(true);
    setError("");
    try {
      await syncContacts(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить контакты");
    } finally {
      setBusy(false);
    }
  }

  if (!visible) return null;

  return (
    <div className={open ? `${styles.root} ${styles.rootOpen}` : styles.root}>
      {open ? (
        <section
          className={styles.panel}
          aria-labelledby={titleId}
          role="dialog"
          aria-modal="true"
        >
          <header className={styles.header}>
            <div className={styles.brandMark} aria-hidden="true">
              <ChatIcon className={styles.brandIcon} />
            </div>
            <div className={styles.headerText}>
              <h2 id={titleId} className={styles.title}>
                Поддержка Hoocon
              </h2>
              <p className={styles.status}>
                <span
                  className={
                    isOpenNow ? styles.statusDotLive : styles.statusDotAway
                  }
                  aria-hidden="true"
                />
                {isOpenNow ? "Сейчас на связи" : "Вне рабочего времени"}
              </p>
            </div>
            <button
              type="button"
              className={styles.close}
              aria-label="Закрыть чат"
              onClick={() => closeSupportChat()}
            >
              <CloseIcon className={styles.closeIcon} />
            </button>
          </header>

          {!isOpenNow && outsideHint ? (
            <p className={styles.banner}>{outsideHint}</p>
          ) : null}

          {!contactsLocked ? (
            <form className={styles.metaDetails} onSubmit={(e) => void onSaveContacts(e)}>
              <p className={styles.metaSummary}>Контакты (необязательно)</p>
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
              <div className={styles.metaActions}>
                <button
                  type="submit"
                  className={styles.metaSave}
                  disabled={busy || (!name.trim() && !email.trim())}
                >
                  Сохранить
                </button>
              </div>
            </form>
          ) : null}

          <div className={styles.messages} ref={listRef}>
            {messages.length === 0 ? (
              <div className={styles.empty}>
                <p className={styles.emptyTitle}>Чем помочь?</p>
                <p className={styles.emptyText}>
                  Вопрос по приводам, арматуре или КП — ответим здесь. Удобнее в
                  Telegram — напишите боту кнопкой ниже.
                </p>
              </div>
            ) : (
              messages.map((m) => {
                const fromVisitor = m.direction === "inbound";
                const time = formatMessageTime(m.created_at);
                const label = m.sender_name || (fromVisitor ? "Вы" : "Поддержка");
                return (
                  <div
                    key={m.id}
                    className={fromVisitor ? styles.rowOut : styles.rowIn}
                  >
                    <span className={styles.sender}>{label}</span>
                    <div
                      className={
                        fromVisitor ? styles.bubbleOut : styles.bubbleIn
                      }
                    >
                      {m.body}
                    </div>
                    {time ? <time className={styles.time}>{time}</time> : null}
                  </div>
                );
              })
            )}
          </div>

          <div className={styles.footerBar}>
            {channels.some((ch) => ch.channel === "telegram_bot") ? (
              <div className={styles.channels}>
                {channels
                  .filter((ch) => ch.channel === "telegram_bot")
                  .map((ch) => (
                    <a
                      key={ch.channel}
                      className={styles.channelChip}
                      href={ch.deep_link}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {ch.label}
                    </a>
                  ))}
              </div>
            ) : null}

            {pushSupported() ? (
              <div className={styles.pushRow}>
                {pushEnabled ? (
                  <span className={styles.pushStatus}>
                    {pushStatus || "Уведомления об ответах включены"}
                  </span>
                ) : (
                  <>
                    <button
                      type="button"
                      className={styles.pushBtn}
                      disabled={pushBusy}
                      onClick={() => void enablePush()}
                    >
                      {pushBusy ? "Подключаем…" : "Уведомлять об ответе"}
                    </button>
                    {pushStatus ? (
                      <span className={styles.pushStatus}>{pushStatus}</span>
                    ) : null}
                  </>
                )}
              </div>
            ) : null}

            <button
              type="button"
              className={styles.hideWidget}
              onClick={() => hideSupportChat()}
            >
              Скрыть чат
            </button>
          </div>

          <form className={styles.composer} onSubmit={(e) => void onSubmit(e)}>
            <label className={styles.srOnly} htmlFor={`${titleId}-draft`}>
              Сообщение
            </label>
            <textarea
              id={`${titleId}-draft`}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={1}
              maxLength={4000}
              placeholder="Напишите сообщение…"
              required
            />
            <button
              type="submit"
              className={styles.send}
              disabled={busy || !draft.trim()}
              aria-label="Отправить"
            >
              <SendIcon className={styles.sendIcon} />
            </button>
          </form>
          {error ? <p className={styles.error}>{error}</p> : null}
        </section>
      ) : null}

      <button
        type="button"
        className={open ? styles.fabOpen : styles.fab}
        aria-expanded={open}
        aria-label={open ? "Закрыть чат" : "Открыть чат поддержки"}
        onClick={() => setSupportChatOpen(!open)}
      >
        {open ? (
          <CloseIcon className={styles.fabIcon} />
        ) : (
          <>
            <ChatIcon className={styles.fabIcon} />
            <span className={styles.fabLabel}>Чат</span>
          </>
        )}
      </button>
    </div>
  );
}
