/**
 * True when highlight/attr key is modulating Y or U signal.
 */
export function isModulatingSignalKey(key: string): boolean {
  const normalized = key.trim().toLowerCase().replace(/-/g, "_");
  return (
    normalized === "control_signal" || normalized === "feedback_signal"
  );
}
