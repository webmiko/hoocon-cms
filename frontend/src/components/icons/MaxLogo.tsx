type MaxLogoProps = {
  className?: string;
  /** Accessible label; set empty to hide from screen readers when text is visible nearby. */
  title?: string;
  /** Include MAX wordmark next to the bubble (footer / wide buttons). */
  withWordmark?: boolean;
};

/**
 * Monochrome MAX messenger mark (`currentColor` — light/dark via CSS).
 * Icon shape aligned with the official bubble; wordmark for wide placements.
 */
export function MaxLogo({
  className,
  title = "MAX",
  withWordmark = false,
}: MaxLogoProps) {
  if (withWordmark) {
    return (
      <svg
        className={className}
        viewBox="0 0 88 24"
        role="img"
        aria-label={title}
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          fill="currentColor"
          d="M12 2C6.48 2 2 5.82 2 10.36c0 2.45 1.24 4.64 3.18 6.1L3.5 22l4.2-2.1c.87.15 1.78.22 2.72.22 5.52 0 10-3.82 10-8.36S17.52 2 12 2Zm0 2c4.2 0 7.6 3.05 7.6 6.8 0 3.76-3.4 6.8-7.6 6.8-.8 0-1.57-.1-2.3-.28l-.22-.06-2.46 1.23.84-2.53-.16-.23C7.35 16.9 6 15.1 6 12.8 6 9.05 9.4 6 12 6Z"
        />
        <path
          fill="currentColor"
          d="M28.2 17.2V6.8h2.6l3.4 6.2 3.4-6.2h2.6v10.4h-2.2V10.1l-3.1 5.6h-1.4l-3.1-5.6v7.1h-2.2Zm17.5.2c-2.5 0-4.3-1.2-4.3-3.4 0-2.1 1.6-3.2 4.8-3.4l1.9-.1v-.5c0-1.1-.8-1.7-2.2-1.7-1.2 0-2 .4-2.5 1.2h-2.1c.5-1.8 2.2-2.9 4.7-2.9 2.9 0 4.5 1.5 4.5 4v5.4h-2l-.2-1c-.6.7-1.7 1.2-3.4 1.2Zm1.5-2.1c1.4 0 2.2-.7 2.2-1.8v-.4l-1.6.1c-1.5.1-2.3.6-2.3 1.5 0 .8.6 1.3 1.7 1.3Zm9.2 2.1c-2.8 0-4.6-1.7-4.6-4.5 0-2.8 1.8-4.5 4.6-4.5s4.6 1.7 4.6 4.5c0 2.8-1.8 4.5-4.6 4.5Zm0-2c1.5 0 2.3-.9 2.3-2.5s-.8-2.5-2.3-2.5-2.3.9-2.3 2.5.8 2.5 2.3 2.5Zm11.2 2.1c-2.2 0-3.6-1.1-3.9-2.9h2.2c.2.8 1 1.2 2 1.2 1.1 0 1.7-.4 1.7-1 0-.6-.5-.9-1.8-1.1l-1.4-.2c-2.1-.3-3.1-1.2-3.1-2.8 0-1.8 1.5-3 3.8-3 2.1 0 3.5 1 3.8 2.7h-2.1c-.2-.7-.9-1.1-1.8-1.1-.9 0-1.5.4-1.5.9 0 .5.4.8 1.6 1l1.5.2c2.2.3 3.2 1.3 3.2 2.9 0 1.9-1.6 3.2-4.2 3.2Z"
        />
      </svg>
    );
  }

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
        d="M12 2C6.48 2 2 5.82 2 10.36c0 2.45 1.24 4.64 3.18 6.1L3.5 22l4.2-2.1c.87.15 1.78.22 2.72.22 5.52 0 10-3.82 10-8.36S17.52 2 12 2Zm0 2c4.2 0 7.6 3.05 7.6 6.8 0 3.76-3.4 6.8-7.6 6.8-.8 0-1.57-.1-2.3-.28l-.22-.06-2.46 1.23.84-2.53-.16-.23C7.35 16.9 6 15.1 6 12.8 6 9.05 9.4 6 12 6Z"
      />
    </svg>
  );
}
