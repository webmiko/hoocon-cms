/** App release label (keep in sync with backend/config/release.py). */

/** Beta: ``X.Y.Z``; after GA: ``MAJOR.MINOR`` (see docs/releases.md). */
export const RELEASE_VERSION = "1.1";
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
 * Public version core without channel (two-part after GA).
 */
export function displayVersion(
  version: string = RELEASE_VERSION,
  channel: string = RELEASE_CHANNEL,
): string {
  const match = VERSION_CORE.exec(version.trim());
  if (!match) return version.trim();
  const [, major, minor, patch] = match;
  if (!channel.trim()) {
    return `${major}.${minor}`;
  }
  if (patch === undefined) {
    return `${major}.${minor}`;
  }
  return `${major}.${minor}.${patch}`;
}

/** Display string, e.g. ``v0.1.0 beta`` or ``v1.0``. */
export function releaseLabel(withV = true): string {
  const prefix = withV ? "v" : "";
  const core = `${prefix}${displayVersion()}`;
  const channel = RELEASE_CHANNEL.trim();
  return channel ? `${core} ${channel}` : core;
}
