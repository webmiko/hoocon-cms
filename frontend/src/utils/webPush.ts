/**
 * Browser / PWA Web Push subscribe helpers (VAPID).
 *
 * PushSubscription lives in the browser across reloads; we re-POST to Django
 * so session_key / topics stay bound after refresh.
 */

import { api } from "../api/client";

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) {
    output[i] = raw.charCodeAt(i);
  }
  return output;
}

/** Some engines want a detached ArrayBuffer, not a Uint8Array view. */
function applicationServerKeyBytes(publicKey: string): ArrayBuffer {
  const bytes = urlBase64ToUint8Array(publicKey);
  return bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  ) as ArrayBuffer;
}

export function pushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

export async function ensureNotificationPermission(): Promise<NotificationPermission> {
  if (!pushSupported()) return "denied";
  if (Notification.permission === "granted") return "granted";
  if (Notification.permission === "denied") return "denied";
  return Notification.requestPermission();
}

async function getRegistration(): Promise<ServiceWorkerRegistration | null> {
  if (!("serviceWorker" in navigator)) return null;
  try {
    const ready = await Promise.race([
      navigator.serviceWorker.ready,
      new Promise<null>((resolve) => {
        window.setTimeout(() => resolve(null), 8000);
      }),
    ]);
    return ready;
  } catch {
    return null;
  }
}

/** True when the browser already has a PushSubscription (survives reload). */
export async function hasBrowserPushSubscription(): Promise<boolean> {
  if (!pushSupported()) return false;
  if (Notification.permission !== "granted") return false;
  const registration = await getRegistration();
  if (!registration) return false;
  try {
    const existing = await registration.pushManager.getSubscription();
    return Boolean(existing);
  } catch {
    return false;
  }
}

export type SubscribeWebPushResult =
  | { ok: true }
  | {
      ok: false;
      reason:
        | "unsupported"
        | "permission"
        | "not_configured"
        | "no_service_worker"
        | "push_service"
        | "subscribe_failed"
        | "api_error";
      detail?: string;
    };

function classifySubscribeError(err: unknown): SubscribeWebPushResult {
  const message = err instanceof Error ? err.message : String(err);
  const name = err instanceof Error ? err.name : "";
  const lower = message.toLowerCase();
  if (
    name === "AbortError" ||
    lower.includes("push service") ||
    lower.includes("registration failed")
  ) {
    return { ok: false, reason: "push_service", detail: message };
  }
  if (name === "NotAllowedError" || lower.includes("permission")) {
    return { ok: false, reason: "permission", detail: message };
  }
  return { ok: false, reason: "subscribe_failed", detail: message };
}

function looksLikeVapidMismatch(err: unknown): boolean {
  const message = (
    err instanceof Error ? err.message : String(err)
  ).toLowerCase();
  return (
    message.includes("applicationserverkey") ||
    message.includes("application server key") ||
    message.includes("gcm sender id") ||
    message.includes("vapid")
  );
}

async function postSubscriptionToApi(
  subscription: PushSubscription,
  topics: { topic_support?: boolean; topic_marketing?: boolean },
): Promise<SubscribeWebPushResult> {
  const json = subscription.toJSON();
  if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
    return { ok: false, reason: "subscribe_failed" };
  }
  const topicMarketing = Boolean(topics.topic_marketing);
  if (topicMarketing) {
    const { isMarketingAllowed, readCookieConsent } = await import(
      "./cookieConsent"
    );
    if (!isMarketingAllowed(readCookieConsent())) {
      return { ok: false, reason: "api_error", detail: "marketing consent required" };
    }
  }
  try {
    await api.fetchCsrfToken();
    await api.webpushSubscribe({
      endpoint: json.endpoint,
      keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
      topic_support: Boolean(topics.topic_support),
      topic_marketing: topicMarketing,
    });
  } catch (err) {
    return {
      ok: false,
      reason: "api_error",
      detail: err instanceof Error ? err.message : String(err),
    };
  }
  return { ok: true };
}

/**
 * If the browser already has a subscription, re-POST it to Django (session bind).
 * Returns null when there is nothing to sync (caller may prompt to subscribe).
 */
export async function syncExistingWebPush(topics: {
  topic_support?: boolean;
  topic_marketing?: boolean;
}): Promise<SubscribeWebPushResult | null> {
  if (!pushSupported()) return null;
  if (Notification.permission !== "granted") return null;
  const registration = await getRegistration();
  if (!registration) return null;
  let existing: PushSubscription | null;
  try {
    existing = await registration.pushManager.getSubscription();
  } catch {
    return null;
  }
  if (!existing) return null;
  return postSubscriptionToApi(existing, topics);
}

/**
 * Subscribe to push topics and POST endpoint to Django.
 * Keeps an existing browser subscription across reloads (does not drop it).
 */
export async function subscribeWebPush(topics: {
  topic_support?: boolean;
  topic_marketing?: boolean;
}): Promise<SubscribeWebPushResult> {
  if (!pushSupported()) return { ok: false, reason: "unsupported" };
  const perm = await ensureNotificationPermission();
  if (perm !== "granted") return { ok: false, reason: "permission" };

  let meta: { public_key: string; configured: boolean };
  try {
    meta = await api.webpushVapidPublicKey();
  } catch (err) {
    return {
      ok: false,
      reason: "api_error",
      detail: err instanceof Error ? err.message : String(err),
    };
  }
  if (!meta.configured || !meta.public_key) {
    return { ok: false, reason: "not_configured" };
  }

  const registration = await getRegistration();
  if (!registration) return { ok: false, reason: "no_service_worker" };

  let subscription: PushSubscription;
  try {
    const existing = await registration.pushManager.getSubscription();
    if (existing) {
      subscription = existing;
    } else {
      const subscribePromise = registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: applicationServerKeyBytes(meta.public_key),
      });
      let timeoutId = 0;
      const raced = await Promise.race([
        subscribePromise.then((sub) => ({ kind: "ok" as const, sub })),
        new Promise<{ kind: "timeout" }>((resolve) => {
          timeoutId = window.setTimeout(() => resolve({ kind: "timeout" }), 15_000);
        }),
      ]);
      window.clearTimeout(timeoutId);

      if (raced.kind === "timeout") {
        // Timeout must not abandon a late PushManager success — otherwise the
        // browser keeps a subscription that never reaches Django until retry.
        void subscribePromise
          .then((sub) => postSubscriptionToApi(sub, topics))
          .catch(() => undefined);
        try {
          const late = await registration.pushManager.getSubscription();
          if (late) {
            return postSubscriptionToApi(late, topics);
          }
        } catch {
          /* fall through to timeout error */
        }
        return {
          ok: false,
          reason: "push_service",
          detail: "PushManager.subscribe timed out",
        };
      }
      subscription = raced.sub;
    }
  } catch (err) {
    // Only drop the browser sub when the key clearly mismatches — never on
    // transient errors (that would make push «fly off» after a refresh).
    if (!looksLikeVapidMismatch(err)) {
      return classifySubscribeError(err);
    }
    try {
      const stale = await registration.pushManager.getSubscription();
      if (stale) await stale.unsubscribe();
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: applicationServerKeyBytes(meta.public_key),
      });
    } catch (retryErr) {
      return classifySubscribeError(retryErr ?? err);
    }
  }

  return postSubscriptionToApi(subscription, topics);
}

/**
 * Sync cookie marketing opt-in to Django session and clear server topic
 * when the visitor turns marketing off.
 */
export async function syncMarketingPushConsent(
  marketingAllowed: boolean,
): Promise<void> {
  try {
    await api.fetchCsrfToken();
    const payload: {
      marketing_consent: boolean;
      endpoint?: string;
      clear_marketing?: boolean;
    } = { marketing_consent: marketingAllowed };
    if (!marketingAllowed && pushSupported()) {
      const registration = await getRegistration();
      const existing = registration
        ? await registration.pushManager.getSubscription()
        : null;
      if (existing?.endpoint) {
        payload.endpoint = existing.endpoint;
        payload.clear_marketing = true;
      }
    }
    await api.webpushTopics(payload);
  } catch {
    /* best-effort — local cookie state remains source of UI truth */
  }
}

/** Short RU status for SupportWidget / marketing prompt. */
export function subscribeWebPushStatusRu(
  result: SubscribeWebPushResult,
): string {
  if (result.ok) return "";
  switch (result.reason) {
    case "unsupported":
      return "Браузер не поддерживает push";
    case "permission":
      return "Нужно разрешить уведомления в браузере";
    case "not_configured":
      return "Push на сервере ещё не настроен";
    case "no_service_worker":
      return "Сервис-воркер ещё не готов — обновите страницу";
    case "push_service":
      return (
        "Браузер не смог подключить push (часто блокировка Google FCM). " +
        "Уведомления могли разрешиться, но доставка недоступна"
      );
    case "api_error":
      return "Ошибка сервера при сохранении подписки";
    default:
      return "Не удалось включить уведомления";
  }
}
