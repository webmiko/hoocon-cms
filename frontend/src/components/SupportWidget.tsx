import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";

import { useFocusTrap } from "../hooks/useFocusTrap";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import {
  closeSupportChat,
  getSupportChatState,
  hideSupportChat,
  setSupportChatOpen,
  subscribeSupportChat,
} from "../utils/supportChatControl";
import {
  countSupportUnread,
  maxSupportMessageId,
  readSupportLastReadId,
  writeSupportLastReadId,
} from "../utils/supportUnread";
import {
  pushSupported,
  subscribeWebPush,
  subscribeWebPushStatusRu,
  syncExistingWebPush,
} from "../utils/webPush";
import { MaxLogo } from "./icons/MaxLogo";
import { MessengerLinks, type MessengerChannel } from "./MessengerLinks";
import styles from "./SupportWidget.module.css";

const SUPPORT_SURFACE_KEY = "hoocon-support-surface";

type ChatMessage = {
  id: number;
  direction: string;
  body: string;
  outside_hours: boolean;
  created_at: string;
  sender_name: string;
};

type SupportSurface = "pick" | "web";

type SupportFaqItem = { id: number; question: string; answer: string };

type SupportConversationState = {
  id: number;
  display_name?: string;
  contact_email?: string;
  ai_active?: boolean;
  ai_escalated?: boolean;
};

const FAQ_PATH_LABELS: Record<string, string> = {
  "/consultation": "консультация",
  "/gde-kupit": "где купить",
  "/kontakty": "контакты",
  "/dokumentaciya": "документация",
  "/catalog": "каталог",
  "/faq": "вопросы и ответы",
  "/zavod": "OEM · завод",
  "/company": "о компании",
  "/rfq": "запрос цены",
};

const FAQ_PATH_RE =
  /\/[a-z0-9][a-z0-9-]*(?:\/[a-z0-9][a-z0-9-]*)*(?:\?[^\s]+)?(?:#[a-z0-9-]+)?/gi;

function faqLinkLabel(href: string): string {
  const [path, query = ""] = href.split(/[?#]/, 2);
  if (path === "/dokumentaciya" && query) {
    const sku = new URLSearchParams(query).get("q");
    if (sku) {
      return `документация: ${sku}`;
    }
  }
  return FAQ_PATH_LABELS[path] ?? href;
}

function faqAnswerNodes(text: string, onNavigate?: () => void): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  const re = new RegExp(FAQ_PATH_RE.source, "gi");
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      nodes.push(text.slice(last, match.index));
    }
    const raw = match[0];
    const trailing = raw.match(/[.,;:!?)\]»"']+$/);
    const href = trailing ? raw.slice(0, -trailing[0].length) : raw;
    const suffix = trailing ? trailing[0] : "";
    nodes.push(
      <Link
        key={`faq-link-${match.index}`}
        to={href}
        className={styles.faqLink}
        onClick={onNavigate}
      >
        {faqLinkLabel(href)}
      </Link>,
    );
    if (suffix) {
      nodes.push(suffix);
    }
    last = match.index + raw.length;
  }
  if (last < text.length) {
    nodes.push(text.slice(last));
  }
  return nodes;
}

function QuickFaqChips({
  items,
  activeId,
  onPick,
}: {
  items: SupportFaqItem[];
  activeId: number | null;
  onPick: (item: SupportFaqItem) => void;
}) {
  if (!items.length) return null;
  return (
    <div className={styles.quickFaq} role="group" aria-label="Частые вопросы">
      <p className={styles.quickFaqLabel}>Частые вопросы</p>
      <div className={styles.quickFaqList}>
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            className={
              item.id === activeId
                ? `${styles.quickFaqChip} ${styles.quickFaqChipActive}`
                : styles.quickFaqChip
            }
            onClick={() => onPick(item)}
          >
            {item.question}
          </button>
        ))}
      </div>
    </div>
  );
}

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

function hasVisitorSentMessage(messages: ChatMessage[]): boolean {
  return messages.some((m) => m.direction === "inbound");
}

function chatStatusText(
  conversation: SupportConversationState | null,
  isOpenNow: boolean,
): string {
  if (conversation?.ai_escalated) {
    return "Передано менеджеру";
  }
  if (conversation?.ai_active) {
    return "Отвечает бот";
  }
  return isOpenNow ? "Сейчас на связи" : "Вне рабочего времени";
}

function readSupportSurfacePref(): SupportSurface | null {
  try {
    const raw = localStorage.getItem(SUPPORT_SURFACE_KEY);
    return raw === "web" ? "web" : null;
  } catch {
    return null;
  }
}

function writeSupportSurfacePref(surface: SupportSurface) {
  try {
    localStorage.setItem(SUPPORT_SURFACE_KEY, surface);
  } catch {
    /* private mode */
  }
}

function hasMessengerBots(channels: MessengerChannel[]): boolean {
  return channels.some(
    (ch) =>
      ch.kind === "bot" ||
      ch.channel === "max_bot" ||
      ch.channel === "telegram_bot",
  );
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
  const [conversation, setConversation] = useState<SupportConversationState | null>(
    null,
  );
  const [draft, setDraft] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [contactsLocked, setContactsLocked] = useState(false);
  const [isOpenNow, setIsOpenNow] = useState(true);
  const [outsideHint, setOutsideHint] = useState("");
  const [channels, setChannels] = useState<MessengerChannel[]>([]);
  const [chatSurface, setChatSurface] = useState<SupportSurface>("web");
  const [faqItems, setFaqItems] = useState<SupportFaqItem[]>([]);
  const [activeFaq, setActiveFaq] = useState<SupportFaqItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pushStatus, setPushStatus] = useState("");
  const [pushEnabled, setPushEnabled] = useState(false);
  const [pushBusy, setPushBusy] = useState(false);
  const [extrasExpanded, setExtrasExpanded] = useState(false);
  const [fabNudge, setFabNudge] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const lastIdRef = useRef(0);
  const lastReadIdRef = useRef(readSupportLastReadId());
  const resumeOnceRef = useRef(false);
  const sessionProbeRef = useRef(false);

  useFocusTrap(panelRef, open);

  function persistReadCursor(messageList: ChatMessage[]) {
    const readId = maxSupportMessageId(messageList, lastReadIdRef.current);
    lastReadIdRef.current = readId;
    writeSupportLastReadId(readId);
  }

  useEffect(
    () =>
      subscribeSupportChat((next) => {
        setVisible(next.visible);
        setOpen(next.open);
        if (!next.open) {
          setFaqItems([]);
          setActiveFaq(null);
          setExtrasExpanded(false);
          writeSupportLastReadId(lastIdRef.current);
          lastReadIdRef.current = lastIdRef.current;
          setUnreadCount(0);
        }
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

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void api
      .supportChatFaq()
      .then((data) => {
        if (!cancelled) setFaqItems(data.items);
      })
      .catch(() => {
        if (!cancelled) setFaqItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  // On open: resume session + full history (PWA reload must see staff replies).
  useEffect(() => {
    if (!open || chatSurface !== "web") {
      resumeOnceRef.current = false;
      return;
    }
    if (resumeOnceRef.current) return;
    resumeOnceRef.current = true;
    let cancelled = false;
    void (async () => {
      try {
        await api.fetchCsrfToken();
        const data = await api.supportMessages();
        if (cancelled) return;
        if (!data.messages.length && !data.conversation) {
          return;
        }
        setStarted(true);
        const conv = data.conversation;
        if (conv?.display_name) {
          setName(conv.display_name);
        }
        if (conv?.contact_email) {
          setEmail(conv.contact_email);
        }
        if (conv?.display_name || conv?.contact_email) {
          setContactsLocked(true);
        }
        setMessages(data.messages);
        if (data.conversation) {
          setConversation(data.conversation);
        }
        lastIdRef.current = maxSupportMessageId(data.messages);
        persistReadCursor(data.messages);
        setUnreadCount(0);
      } catch {
        /* first message creates the thread on send */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, chatSurface]);

  // Resume session while FAB is closed — poll for staff/bot replies + unread badge.
  useEffect(() => {
    if (open || chatSurface !== "web" || sessionProbeRef.current) return;
    sessionProbeRef.current = true;
    let cancelled = false;
    void (async () => {
      try {
        await api.fetchCsrfToken();
        const data = await api.supportMessages();
        if (cancelled || (!data.messages.length && !data.conversation)) return;
        setStarted(true);
        setMessages(data.messages);
        if (data.conversation) {
          setConversation(data.conversation);
        }
        lastIdRef.current = maxSupportMessageId(data.messages);
        setUnreadCount(countSupportUnread(data.messages, lastReadIdRef.current));
      } catch {
        /* no session yet */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, chatSurface]);

  useEffect(() => {
    if (chatSurface !== "web" || !started) return;
    const tick = async () => {
      try {
        const after = lastIdRef.current > 0 ? lastIdRef.current : undefined;
        const data = await api.supportMessages(after);
        if (data.conversation) {
          setConversation(data.conversation);
        }
        if (!data.messages.length) return;
        setMessages((prev) => mergeMessages(prev, data.messages));
        lastIdRef.current = maxSupportMessageId(
          data.messages,
          lastIdRef.current,
        );
        if (open) {
          persistReadCursor(data.messages);
        } else {
          const incomingUnread = data.messages.filter(
            (m) => m.direction !== "inbound" && m.id > lastReadIdRef.current,
          ).length;
          if (incomingUnread > 0) {
            setUnreadCount((prev) => prev + incomingUnread);
          }
        }
      } catch {
        /* ignore transient poll errors (network); do not starve UI */
      }
    };
    void tick();
    const intervalMs = open ? 2500 : 4000;
    const id = window.setInterval(() => void tick(), intervalMs);
    return () => window.clearInterval(id);
  }, [open, started, chatSurface]);

  useEffect(() => {
    const el = listRef.current;
    if (!el || !open) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, open, activeFaq]);

  function pickFaq(item: SupportFaqItem) {
    setActiveFaq((prev) => (prev?.id === item.id ? null : item));
  }

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

  // Working hours: subtle FAB nudge — first after 5s, then every 10s (5 hops each).
  const canRunFabNudge = visible && !open && isOpenNow;

  useEffect(() => {
    if (!canRunFabNudge) {
      return;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }

    let intervalId: number | undefined;
    let nudgeOffId: number | undefined;

    const runNudge = () => {
      setFabNudge(true);
      nudgeOffId = window.setTimeout(() => setFabNudge(false), 1500);
    };

    const initialId = window.setTimeout(() => {
      runNudge();
      intervalId = window.setInterval(runNudge, 10_000);
    }, 5_000);

    return () => {
      window.clearTimeout(initialId);
      if (intervalId !== undefined) {
        window.clearInterval(intervalId);
      }
      if (nudgeOffId !== undefined) {
        window.clearTimeout(nudgeOffId);
      }
      setFabNudge(false);
    };
  }, [canRunFabNudge]);

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
      return;
    }
    await api.fetchCsrfToken();
    const conv = await api.supportStartConversation({
      display_name: displayName || undefined,
      contact_email: contactEmail || undefined,
    });
    setConversation({
      id: conv.id ?? 0,
      display_name: conv.display_name,
      contact_email: conv.contact_email,
      ai_active: conv.ai_active,
      ai_escalated: conv.ai_escalated,
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

  function onDraftKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey) return;
    if (event.nativeEvent.isComposing || event.keyCode === 229) return;
    event.preventDefault();
    if (busy || !draft.trim()) return;
    event.currentTarget.form?.requestSubmit();
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
      setStarted(true);
      const next = [result.message];
      if (result.auto_reply) next.push(result.auto_reply);
      setMessages((prev) => {
        const merged = mergeMessages(prev, next);
        lastIdRef.current = maxSupportMessageId(next, lastIdRef.current);
        if (open) {
          persistReadCursor(merged);
        }
        return merged;
      });
      setDraft("");
      setActiveFaq(null);
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

  function chooseWebChat() {
    writeSupportSurfacePref("web");
    setChatSurface("web");
  }

  function showChannelPicker() {
    setChatSurface("pick");
  }

  const showPicker = open && chatSurface === "pick" && hasMessengerBots(channels);
  const chatEngaged = hasVisitorSentMessage(messages);
  const showExtras = !chatEngaged || extrasExpanded;

  if (!visible) return null;

  return (
    <div className={open ? `${styles.root} ${styles.rootOpen}` : styles.root}>
      {open ? (
        <section
          ref={panelRef}
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
                {chatStatusText(conversation, isOpenNow)}
              </p>
              {chatSurface === "web" && hasMessengerBots(channels) ? (
                <button
                  type="button"
                  className={styles.surfaceSwitch}
                  onClick={showChannelPicker}
                >
                  Другой способ связи
                </button>
              ) : null}
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

          {showPicker ? (
            <div className={styles.surfacePicker}>
              <p className={styles.surfaceTitle}>Как удобнее связаться?</p>
              <p className={styles.surfaceHint}>
                Чат на сайте или личные сообщения в MAX / Telegram — ответим в
                рабочие дни.
              </p>
              <button
                type="button"
                className={styles.surfacePrimary}
                onClick={chooseWebChat}
              >
                <ChatIcon className={styles.surfacePrimaryIcon} />
                <span>
                  <strong>Чат на сайте</strong>
                  <small>Без установки приложений</small>
                </span>
              </button>
              <MessengerLinks
                channels={channels}
                variant="compact"
                onNavigate={() => closeSupportChat()}
              />
            </div>
          ) : null}

          {!showPicker && conversation?.ai_escalated ? (
            <p className={styles.banner}>
              Чат передан менеджеру — дальше ответит человек. Ожидайте, пожалуйста.
            </p>
          ) : null}

          {!showPicker && !conversation?.ai_escalated && !isOpenNow && outsideHint ? (
            <p className={styles.banner}>{outsideHint}</p>
          ) : null}

          {!showPicker && !contactsLocked ? (
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

          {!showPicker ? (
          <div className={styles.messages} ref={listRef}>
            {messages.length === 0 && !activeFaq ? (
              <div className={styles.empty}>
                <p className={styles.emptyTitle}>Чем помочь?</p>
                <p className={styles.emptyText}>
                  Вопрос по приводам, арматуре или КП — ответим здесь. Удобнее в
                  MAX или Telegram — кнопки ниже.
                </p>
              </div>
            ) : null}
            {messages.map((m) => {
                const fromVisitor = m.direction === "inbound";
                const isBot = m.direction === "system";
                const time = formatMessageTime(m.created_at);
                const label = m.sender_name || (fromVisitor ? "Вы" : "Поддержка");
                const rowClass = fromVisitor
                  ? styles.rowOut
                  : isBot
                    ? styles.rowBot
                    : styles.rowIn;
                const bubbleClass = fromVisitor
                  ? styles.bubbleOut
                  : isBot
                    ? styles.bubbleBot
                    : styles.bubbleIn;
                return (
                  <div key={m.id} className={rowClass}>
                    <span className={styles.sender}>{label}</span>
                    <div className={bubbleClass}>
                      {isBot
                        ? faqAnswerNodes(m.body, () => closeSupportChat())
                        : m.body}
                    </div>
                    {time ? <time className={styles.time}>{time}</time> : null}
                  </div>
                );
              })}
            {activeFaq ? (
              <>
                <div className={styles.rowOut}>
                  <span className={styles.sender}>Вы</span>
                  <div className={styles.bubbleOut}>{activeFaq.question}</div>
                </div>
                <div className={styles.rowIn}>
                  <span className={styles.sender}>Поддержка</span>
                  <div className={styles.bubbleIn}>
                    {faqAnswerNodes(activeFaq.answer, () => closeSupportChat())}
                  </div>
                </div>
              </>
            ) : null}
          </div>
          ) : null}

          {!showPicker && chatEngaged ? (
            <div className={styles.extrasToggleRow}>
              <button
                type="button"
                className={styles.extrasToggle}
                aria-expanded={extrasExpanded}
                onClick={() => setExtrasExpanded((expanded) => !expanded)}
              >
                <span className={styles.extrasToggleLabel}>
                  {extrasExpanded ? "Свернуть подсказки" : "Подсказки и связь"}
                </span>
                <span
                  className={
                    extrasExpanded
                      ? `${styles.extrasChevron} ${styles.extrasChevronOpen}`
                      : styles.extrasChevron
                  }
                  aria-hidden="true"
                />
              </button>
            </div>
          ) : null}

          {!showPicker && showExtras ? (
          <QuickFaqChips
            items={faqItems}
            activeId={activeFaq?.id ?? null}
            onPick={pickFaq}
          />
          ) : null}

          {!showPicker && showExtras ? (
          <div className={styles.footerBar}>
            {hasMessengerBots(channels) ? (
              <MessengerLinks channels={channels} variant="compact" />
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
          ) : null}

          {!showPicker ? (
          <form className={styles.composer} onSubmit={(e) => void onSubmit(e)}>
            <div className={styles.composerMain}>
              <label className={styles.srOnly} htmlFor={`${titleId}-draft`}>
                Сообщение
              </label>
              <textarea
                id={`${titleId}-draft`}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={onDraftKeyDown}
                rows={2}
                maxLength={4000}
                placeholder="Сообщение…"
                enterKeyHint="enter"
                aria-describedby={`${titleId}-composer-hint`}
                required
              />
              <p className={styles.composerHint} id={`${titleId}-composer-hint`}>
                Enter — отправить · Shift+Enter — новая строка
              </p>
            </div>
            <button
              type="submit"
              className={styles.send}
              disabled={busy || !draft.trim()}
              aria-label="Отправить"
            >
              <SendIcon className={styles.sendIcon} />
            </button>
          </form>
          ) : null}
          {error ? <p className={styles.error}>{error}</p> : null}
        </section>
      ) : null}

      <button
        type="button"
        className={
          open
            ? styles.fabOpen
            : [
                styles.fab,
                isOpenNow ? styles.fabLive : styles.fabAway,
                fabNudge && canRunFabNudge ? styles.fabNudge : "",
              ]
                .filter(Boolean)
                .join(" ")
        }
        aria-expanded={open}
        aria-label={
          open
            ? "Закрыть чат"
            : unreadCount > 0
              ? `Открыть чат поддержки, ${unreadCount} новых сообщений`
              : "Открыть чат поддержки"
        }
        onClick={() => {
          if (!open) {
            setChatSurface(
              hasMessengerBots(channels)
                ? (readSupportSurfacePref() ?? "pick")
                : "web",
            );
          }
          setSupportChatOpen(!open);
        }}
      >
        {open ? (
          <CloseIcon className={styles.fabIcon} />
        ) : (
          <>
            {channels.some((ch) => ch.provider === "max" || ch.channel.startsWith("max_")) ? (
              <MaxLogo className={styles.fabMaxIcon} title="" />
            ) : (
              <ChatIcon className={styles.fabIcon} />
            )}
            <span className={styles.fabLabel}>Чат</span>
            {unreadCount > 0 ? (
              <span className={styles.fabBadge} aria-hidden="true">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            ) : null}
          </>
        )}
      </button>
    </div>
  );
}
