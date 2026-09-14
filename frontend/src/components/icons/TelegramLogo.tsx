type TelegramLogoProps = {
  className?: string;
  title?: string;
};

/** Monochrome Telegram plane (`currentColor`). */
export function TelegramLogo({ className, title = "Telegram" }: TelegramLogoProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      role="img"
      aria-label={title}
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        fill="currentColor"
        d="M21.95 4.57a1.5 1.5 0 0 0-1.53-.25L2.91 11.1c-1.12.47-1.1 2.12.03 2.56l4.58 1.7 1.76 5.58a1.12 1.12 0 0 0 1.78.45l2.52-2.45 4.95 3.65c.98.72 2.37.17 2.6-1.08l2.92-16.94ZM9.4 13.77l7.9-4.9-6.1 5.9-.28 3.02-1.52-4.02Z"
      />
    </svg>
  );
}
