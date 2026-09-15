import * as Sentry from "@sentry/react";

import { packageVersion } from "./release";

/**
 * Initialize browser error tracking when VITE_SENTRY_DSN is set.
 */
export function initSentry(): void {
  const dsn = (import.meta.env.VITE_SENTRY_DSN as string | undefined)?.trim();
  if (!dsn) {
    return;
  }

  const tracesRaw = (
    import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE as string | undefined
  )?.trim();
  const tracesSampleRate = tracesRaw ? Number(tracesRaw) : 0;

  Sentry.init({
    dsn,
    environment: import.meta.env.MODE,
    release: `hoocon-cms@${packageVersion()}`,
    integrations: [Sentry.browserTracingIntegration()],
    tracesSampleRate: Number.isFinite(tracesSampleRate) ? tracesSampleRate : 0,
    sendDefaultPii: false,
  });
}
