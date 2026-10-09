import { ApiError } from "../api/client";

/** Only a real API 404 (or an empty payload) is «не найдено»; the rest is a failed load. */
export function isNotFoundError(error: unknown): boolean {
  return !error || (error instanceof ApiError && error.status === 404);
}
