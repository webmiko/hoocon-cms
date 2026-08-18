import { RELEASE_VERSION } from "../release";

export const RELEASE_RELOAD_STORAGE_KEY = "hoocon.release-reload.v1";

type HealthPayload = {
  version?: string;
};

function readReloadTarget(): string | null {
  if (typeof sessionStorage === "undefined") return null;
  try {
    return sessionStorage.getItem(RELEASE_RELOAD_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeReloadTarget(version: string): void {
  if (typeof sessionStorage === "undefined") return;
  try {
    sessionStorage.setItem(RELEASE_RELOAD_STORAGE_KEY, version);
  } catch {
    // private mode / quota — still attempt reload below
  }
}

/**
 * Reload once when ``/api/health/`` reports a newer release than this bundle.
 *
 * Complements hashed Vite assets + SW autoUpdate: a tab that kept an old
 * shell still picks up the deploy without a manual hard refresh.
 */
export async function reloadIfReleaseStale(
  fetchHealth: () => Promise<HealthPayload> = fetchHealthVersion,
  reload: () => void = () => {
    window.location.reload();
  },
): Promise<boolean> {
  let remote: string | undefined;
  try {
    remote = (await fetchHealth()).version;
  } catch {
    return false;
  }
  if (!remote || remote === RELEASE_VERSION) {
    return false;
  }
  if (readReloadTarget() === remote) {
    return false;
  }
  writeReloadTarget(remote);
  reload();
  return true;
}

async function fetchHealthVersion(): Promise<HealthPayload> {
  const response = await fetch("/api/health/", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`health ${response.status}`);
  }
  return (await response.json()) as HealthPayload;
}
