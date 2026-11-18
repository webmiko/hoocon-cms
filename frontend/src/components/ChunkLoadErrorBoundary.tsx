import { Component, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { isChunkLoadError, recoverFromStaleChunk } from "../utils/chunkLoadRecovery";
import { serverCrawlIsShowing } from "../utils/serverCrawl";
import styles from "./ChunkLoadErrorBoundary.module.css";

type Props = {
  children: ReactNode;
  /** Shown when recovery already ran once this session. */
  fallback?: ReactNode;
  /** Clears a caught error when it changes (route pathname). */
  resetKey?: string;
};

type State = {
  error: Error | null;
};

function ReloadPrompt({ message }: { message: string }) {
  return (
    <div className={styles.root} role="alert">
      <p>{message}</p>
      <p>
        <button type="button" className={styles.button} onClick={() => window.location.reload()}>
          Обновить
        </button>
      </p>
    </div>
  );
}

/**
 * While the server article is the visible page, do not replace it with the
 * crash sentence — that sentence was becoming the Yandex snippet.
 */
function CrawlReloadButton() {
  const article = document.getElementById("seo-crawl");
  if (!article) return null;
  return createPortal(
    <p>
      <button type="button" className={styles.button} onClick={() => window.location.reload()}>
        Обновить страницу
      </button>
    </p>,
    article,
  );
}

/**
 * Catches render-time chunk failures that slip past ``lazy`` (e.g. SW race)
 * and triggers one hard reload; otherwise shows ``fallback``.
 */
export class ChunkLoadErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error): void {
    recoverFromStaleChunk(error);
  }

  componentDidUpdate(prevProps: Props): void {
    if (this.state.error && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  render(): ReactNode {
    const { error } = this.state;
    if (!error) {
      return this.props.children;
    }
    if (serverCrawlIsShowing()) {
      return <CrawlReloadButton />;
    }
    if (isChunkLoadError(error) && this.props.fallback != null) {
      return this.props.fallback;
    }
    if (isChunkLoadError(error)) {
      return <ReloadPrompt message="Не удалось загрузить страницу после обновления сайта." />;
    }
    return <ReloadPrompt message="Произошла ошибка. Попробуйте обновить страницу." />;
  }
}
