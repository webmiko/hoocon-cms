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

function iconClass(
  provider: "max" | "telegram",
  variant: "compact" | "footer",
): string {
  if (provider === "max") {
    return variant === "footer" ? styles.footerIconMax : styles.compactIconMax;
  }
  return variant === "footer" ? styles.footerIconTelegram : styles.compactIconTelegram;
}

function MessengerIcon({
  provider,
  className,
  withWordmark = false,
}: {
  provider: "max" | "telegram";
  className?: string;
  withWordmark?: boolean;
}) {
  const title = provider === "max" ? "MAX" : "Telegram";
  if (provider === "max") {
    return <MaxLogo className={className} withWordmark={withWordmark} title={title} />;
  }
  return <TelegramLogo className={className} withWordmark={withWordmark} title={title} />;
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
    <ul className={rootClass} role="list" aria-label="Мессенджеры">
      {items.map((ch) => {
        const provider = providerFor(ch);
        const withWordmark = provider === "max" || provider === "telegram";
        return (
          <li key={ch.channel}>
            <a
              className={
                variant === "footer" ? styles.footerLink : styles.compactLink
              }
              href={ch.deep_link}
              target="_blank"
              rel="noopener noreferrer"
              onClick={onNavigate}
            >
              {provider ? (
                <MessengerIcon
                  provider={provider}
                  className={iconClass(provider, variant)}
                  withWordmark={withWordmark}
                />
              ) : null}
            </a>
          </li>
        );
      })}
    </ul>
  );
}
