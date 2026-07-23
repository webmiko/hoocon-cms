/** App release label (keep in sync with backend/config/release.py). */

export const RELEASE_VERSION = "0.0.7";
export const RELEASE_CHANNEL = "beta";

/** Display string, e.g. ``v0.0.7 beta``. */
export function releaseLabel(withV = true): string {
  const prefix = withV ? "v" : "";
  const core = `${prefix}${RELEASE_VERSION}`;
  const channel = RELEASE_CHANNEL.trim();
  return channel ? `${core} ${channel}` : core;
}
