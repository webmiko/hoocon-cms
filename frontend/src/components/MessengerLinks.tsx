import { MaxLogo } from "./icons/MaxLogo";
import { TelegramLogo } from "./icons/TelegramLogo";
import styles from "./MessengerLinks.module.css";

export type MessengerChannel = {
  channel: string;
  label: string;
  deep_link: string;
  provider?: string;
  kind?: string;
};

function providerFor(channel: MessengerChannel): "max" | "telegram" | null {
  if (channel.provider === "max" || channel.channel.startsWith("max_")) {
    return "max";
  }
  if (channel.provider === "telegram" || channel.channel.startsWith("telegram_")) {
    return "telegram";
  }
  return null;
}

function MessengerIcon({
  provider,
  className,
}: {
  provider: "max" | "telegram";
  className?: string;
}) {
  if (provider === "max") {
    return <MaxLogo className={className} withWordmark />;
  }
  return <TelegramLogo className={className} />;
}

type MessengerLinksProps = {
  channels: MessengerChannel[];
  /** compact — icon + short label (widget); footer — icon tiles on dark bg */
  variant?: "compact" | "footer";
  onNavigate?: () => void;
};

/**
 * External messenger deep links with official monochrome marks.
 */
export function MessengerLinks({
  channels,
  variant = "compact",
  onNavigate,
}: MessengerLinksProps) {
  const items = channels.filter(
    (ch) => ch.kind === "bot" || ch.channel.endsWith("_bot"),
  );
  if (!items.length) return null;

  const rootClass =
    variant === "footer" ? styles.footerRow : styles.compactRow;

  return (
    <div className={rootClass} role="list" aria-label="Мессенджеры">
      {items.map((ch) => {
        const provider = providerFor(ch);
        const shortLabel = provider === "max" ? "MAX" : "Telegram";
        return (
          <a
            key={ch.channel}
            className={
              variant === "footer" ? styles.footerLink : styles.compactLink
            }
            href={ch.deep_link}
            target="_blank"
            rel="noopener noreferrer"
            role="listitem"
            onClick={onNavigate}
          >
            {provider ? (
              <MessengerIcon
                provider={provider}
                className={
                  variant === "footer" ? styles.footerIcon : styles.compactIcon
                }
              />
            ) : null}
            <span className={styles.linkLabel}>{shortLabel}</span>
          </a>
        );
      })}
    </div>
  );
}
