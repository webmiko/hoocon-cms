type VkLogoProps = {
  className?: string;
  /** Accessible label; set empty to hide from screen readers when text is visible nearby. */
  title?: string;
  /** Tight letterform canvas — the VK mark is a wordmark itself (footer / wide buttons). */
  withWordmark?: boolean;
};

/** Official VK badge mark — rounded square with the letterform knocked out. */
const BADGE_PATH =
  "m9.489.004.729-.003h3.564l.73.003.914.01.433.007.418.011.403.014.388.016.374.021" +
  ".36.025.345.03.333.033c1.74.196 2.933.616 3.833 1.516.9.9 1.32 2.092 1.516 3.833" +
  "l.034.333.029.346.025.36.02.373.025.588.012.41.013.644.009.915.004.98-.001 3.313" +
  "-.003.73-.01.914-.007.433-.011.418-.014.403-.016.388-.021.374-.025.36-.03.345" +
  "-.033.333c-.196 1.74-.616 2.933-1.516 3.833-.9.9-2.092 1.32-3.833 1.516l-.333" +
  ".034-.346.029-.36.025-.373.02-.588.025-.41.012-.644.013-.915.009-.98.004-3.313" +
  "-.001-.73-.003-.914-.01-.433-.007-.418-.011-.403-.014-.388-.016-.374-.021-.36" +
  "-.025-.345-.03-.333-.033c-1.74-.196-2.933-.616-3.833-1.516-.9-.9-1.32-2.092" +
  "-1.516-3.833l-.034-.333-.029-.346-.025-.36-.02-.373-.025-.588-.012-.41-.013" +
  "-.644-.009-.915-.004-.98.001-3.313.003-.73.01-.914.007-.433.011-.418.014" +
  "-.403.016-.388.021-.374.025-.36.03-.345.033-.333c.196-1.74.616-2.933 1.516" +
  "-3.833.9-.9 2.092-1.32 3.833-1.516l.333-.034.346-.029.36-.025.373-.02.588" +
  "-.025.41-.012.644-.013.915-.009Z";

/** VK letterform alone (the wordmark itself), occupies x 4–20.1, y 7.3–17.3. */
const LETTER_PATH =
  "M6.79 7.3H4.05c.13 6.24 3.25 9.99 8.72 9.99h.31v-3.57c2.01.2 3.53 1.67 4.14 " +
  "3.57h2.84c-.78-2.84-2.83-4.41-4.11-5.01 1.28-.74 3.08-2.54 3.51-4.98h-2.58" +
  "c-.56 1.98-2.22 3.78-3.8 3.95V7.3H10.5v6.92c-1.6-.4-3.62-2.34-3.71-6.92Z";

/**
 * Monochrome VK mark (`currentColor` — light/dark via CSS).
 * Geometry from the official VK logo (simple-icons vk.svg, 24×24).
 */
export function VkLogo({
  className,
  title = "VK",
  withWordmark = false,
}: VkLogoProps) {
  const hidden = title === "";
  const a11y = hidden
    ? { "aria-hidden": true as const }
    : { role: "img" as const, "aria-label": title };

  if (withWordmark) {
    return (
      <svg
        className={className}
        viewBox="4 7.3 17 10"
        {...a11y}
        xmlns="http://www.w3.org/2000/svg"
      >
        <path fill="currentColor" d={LETTER_PATH} />
      </svg>
    );
  }

  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      {...a11y}
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        fill="currentColor"
        fillRule="evenodd"
        clipRule="evenodd"
        d={BADGE_PATH}
      />
    </svg>
  );
}
