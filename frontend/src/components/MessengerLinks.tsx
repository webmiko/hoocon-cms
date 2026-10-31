import { MaxLogo } from "./icons/MaxLogo";
import { TelegramLogo } from "./icons/TelegramLogo";
import { VkLogo } from "./icons/VkLogo";
import styles from "./MessengerLinks.module.css";

export type MessengerChannel = {
  channel: string;
  label: string;
  deep_link: string;
  provider?: string;
  kind?: string;
};

type MessengerProvider = "max" | "telegram" | "vk";

function providerFor(channel: MessengerChannel): MessengerProvider | null {
  if (channel.provider === "max" || channel.channel.startsWith("max_")) {
    return "max";
  }
  if (channel.provider === "telegram" || channel.channel.startsWith("telegram_")) {
    return "telegram";
  }
  if (channel.provider === "vk" || channel.channel.startsWith("vk_")) {
    return "vk";
  }
  return null;
}

function iconClass(
  provider: MessengerProvider,
  variant: "compact" | "footer",
): string {
  if (provider === "max") {
    return variant === "footer" ? styles.footerIconMax : styles.compactIconMax;
  }
  if (provider === "vk") {
    return variant === "footer" ? styles.footerIconVk : styles.compactIconVk;
  }
  return variant === "footer" ? styles.footerIconTelegram : styles.compactIconTelegram;
}

function MessengerIcon({
  provider,
  className,
  withWordmark = false,
}: {
  provider: MessengerProvider;
  className?: string;
  withWordmark?: boolean;
}) {
  const title = provider === "max" ? "MAX" : provider === "vk" ? "VK" : "Telegram";
  if (provider === "max") {
    return <MaxLogo className={className} withWordmark={withWordmark} title={title} />;
  }
  if (provider === "vk") {
    return <VkLogo className={className} withWordmark={withWordmark} title={title} />;
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
        const withWordmark = provider !== null;
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
              ) : (
                ch.label
              )}
            </a>
          </li>
        );
      })}
    </ul>
  );
}
