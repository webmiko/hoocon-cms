/**
 * Browser / PWA Web Push subscribe helpers (VAPID).
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
function applicationServerKeyBytes(publicKey: string): BufferSource {
  const bytes = urlBase64ToUint8Array(publicKey);
  return bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  );
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

/**
 * Subscribe to push topics and POST endpoint to Django.
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

  try {
    await api.fetchCsrfToken();
  } catch (err) {
    return {
      ok: false,
      reason: "api_error",
      detail: err instanceof Error ? err.message : String(err),
    };
  }

  let subscription: PushSubscription;
  try {
    const existing = await registration.pushManager.getSubscription();
    subscription =
      existing ??
      (await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: applicationServerKeyBytes(meta.public_key),
      }));
  } catch (err) {
    // Stale subscription bound to an old VAPID key — drop and retry once.
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

  const json = subscription.toJSON();
  if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
    return { ok: false, reason: "subscribe_failed" };
  }
  try {
    await api.webpushSubscribe({
      endpoint: json.endpoint,
      keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
      topic_support: Boolean(topics.topic_support),
      topic_marketing: Boolean(topics.topic_marketing),
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
      return "Push-сервис браузера недоступен (Chrome/FCM или поставьте PWA)";
    case "api_error":
      return "Ошибка сервера при сохранении подписки";
    default:
      return "Не удалось включить уведомления";
  }
}
