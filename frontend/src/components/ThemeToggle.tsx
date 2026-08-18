import { useTheme } from "../theme/ThemeContext";
import type { ThemePreference } from "../utils/theme";

import styles from "./ThemeToggle.module.css";

type ThemeToggleProps = {
  /** Extra class on the icon button (layout spacing). */
  className?: string;
  /** Show a text label beside the control (mobile panel). */
  showLabel?: boolean;
};

function ThemeIcon({ preference }: { preference: ThemePreference }) {
  if (preference === "light") {
    return (
      <svg className={styles.icon} viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" strokeWidth="1.75" />
        <path
          d={
            "M12 3v2.2 M12 18.8V21 M3 12h2.2 M18.8 12H21 "
            + "M5.6 5.6l1.6 1.6 M16.8 16.8l1.6 1.6 "
            + "M5.6 18.4l1.6-1.6 M16.8 7.2l1.6-1.6"
          }
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (preference === "dark") {
    return (
      <svg className={styles.icon} viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M15.2 3.2a8.8 8.8 0 1 0 5.6 15.4A7.2 7.2 0 0 1 15.2 3.2z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  return (
    <svg className={styles.icon} viewBox="0 0 24 24" aria-hidden="true">
      <circle
        cx="12"
        cy="12"
        r="8"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
      />
      <path
        d="M12 4a8 8 0 0 0 0 16Z"
        fill="currentColor"
      />
    </svg>
  );
}

/**
 * Cycles theme preference: system → light → dark → system.
 * Spec: OS auto via prefers-color-scheme when preference is system.
 */
export function ThemeToggle({ className, showLabel = false }: ThemeToggleProps) {
  const { preference, label, cyclePreference } = useTheme();
  const nextHint =
    preference === "system"
      ? "Переключить на светлую тему"
      : preference === "light"
        ? "Переключить на тёмную тему"
        : "Переключить на тему устройства";

  const button = (
    <button
      type="button"
      className={className ? `${styles.toggle} ${className}` : styles.toggle}
      onClick={cyclePreference}
      aria-label={`${label}. ${nextHint}`}
      title={label}
    >
      <ThemeIcon preference={preference} />
    </button>
  );

  if (!showLabel) {
    return button;
  }

  return (
    <div className={styles.row}>
      <span className={styles.rowLabel}>{label}</span>
      {button}
    </div>
  );
}
