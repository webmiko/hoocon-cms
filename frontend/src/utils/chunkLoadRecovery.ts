/**
 * Recover from stale Vite/PWA assets after deploy: old shell + missing chunks.
 * One hard reload per tab session; second failure surfaces to the UI.
 */

export const CHUNK_RELOAD_STORAGE_KEY = "hoocon.chunk-reload.v1";

const CHUNK_LOAD_ERROR_RE =
  /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Loading chunk [\w-]+ failed|ChunkLoadError/i;

/**
 * Whether ``error`` looks like a failed dynamic import / code-split chunk.
 */
export function isChunkLoadError(error: unknown): boolean {
  if (error == null) return false;
  if (typeof error === "string") {
    return CHUNK_LOAD_ERROR_RE.test(error);
  }
  if (error instanceof Error) {
    if (CHUNK_LOAD_ERROR_RE.test(error.message)) return true;
    if (error.name === "ChunkLoadError") return true;
    return false;
  }
  if (typeof error === "object" && "message" in error) {
    const msg = (error as { message?: unknown }).message;
    return typeof msg === "string" && CHUNK_LOAD_ERROR_RE.test(msg);
  }
  return false;
}

function readReloadFlag(): boolean {
  if (typeof sessionStorage === "undefined") return false;
  try {
    return sessionStorage.getItem(CHUNK_RELOAD_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeReloadFlag(): void {
  if (typeof sessionStorage === "undefined") return;
  try {
    sessionStorage.setItem(CHUNK_RELOAD_STORAGE_KEY, "1");
  } catch {
    // private mode / quota — still attempt reload below
  }
}

/**
 * Clear the one-shot reload guard after a successful boot.
 */
export function clearChunkReloadFlag(): void {
  if (typeof sessionStorage === "undefined") return;
  try {
    sessionStorage.removeItem(CHUNK_RELOAD_STORAGE_KEY);
  } catch {
    // ignore
  }
}

/**
 * If ``error`` is a stale-chunk failure and we have not reloaded yet, reload
 * once and return true. Otherwise return false (caller should surface the error).
 */
export function recoverFromStaleChunk(
  error: unknown,
  reload: () => void = () => {
    window.location.reload();
  },
): boolean {
  if (!isChunkLoadError(error)) return false;
  if (readReloadFlag()) {
    clearChunkReloadFlag();
    return false;
  }
  writeReloadFlag();
  reload();
  return true;
}
