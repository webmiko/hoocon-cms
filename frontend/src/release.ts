/** App release label (keep in sync with backend/config/release.py). */

/**
 * Beta and GA both show ``MAJOR.MINOR.PATCH`` (``v3.6.0``).
 * MINOR is a new feature; PATCH is a fix; MAJOR is manual.
 */
export const RELEASE_VERSION = "3.8.11";
export const RELEASE_CHANNEL = "";

const VERSION_CORE = /^(\d+)\.(\d+)(?:\.(\d+))?$/;

/**
 * SemVer ``X.Y.Z`` for package.json (GA two-part → patch ``0``).
 */
export function packageVersion(version: string = RELEASE_VERSION): string {
  const match = VERSION_CORE.exec(version.trim());
  if (!match) {
    throw new Error(`Invalid RELEASE_VERSION ${version}; expected X.Y or X.Y.Z`);
  }
  const [, major, minor, patch] = match;
  return `${major}.${minor}.${patch ?? "0"}`;
}

/**
 * Public version core: always three numbers. A missing patch becomes ``0``.
 */
export function displayVersion(version: string = RELEASE_VERSION): string {
  const match = VERSION_CORE.exec(version.trim());
  if (!match) return version.trim();
  const [, major, minor, patch] = match;
  return `${major}.${minor}.${patch ?? "0"}`;
}

/** Display string, e.g. ``v0.1.0 beta`` or ``v3.6.0``. */
export function releaseLabel(withV = true): string {
  const prefix = withV ? "v" : "";
  const core = `${prefix}${displayVersion()}`;
  const channel = RELEASE_CHANNEL.trim();
  return channel ? `${core} ${channel}` : core;
}
