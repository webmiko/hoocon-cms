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
    return await navigator.serviceWorker.ready;
  } catch {
    return null;
  }
}

/**
 * Subscribe to push topics and POST endpoint to Django.
 */
export async function subscribeWebPush(topics: {
  topic_support?: boolean;
  topic_marketing?: boolean;
}): Promise<boolean> {
  if (!pushSupported()) return false;
  const perm = await ensureNotificationPermission();
  if (perm !== "granted") return false;

  const meta = await api.webpushVapidPublicKey();
  if (!meta.configured || !meta.public_key) return false;

  const registration = await getRegistration();
  if (!registration) return false;

  await api.fetchCsrfToken();
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(
        meta.public_key,
      ) as BufferSource,
    });
  }
  const json = subscription.toJSON();
  if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) return false;
  await api.webpushSubscribe({
    endpoint: json.endpoint,
    keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
    topic_support: Boolean(topics.topic_support),
    topic_marketing: Boolean(topics.topic_marketing),
  });
  return true;
}
