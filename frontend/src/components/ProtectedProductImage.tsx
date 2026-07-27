import {
  useEffect,
  useRef,
  useState,
  type ImgHTMLAttributes,
} from "react";

import { useProtectedMediaSrc } from "../hooks/useProtectedMediaSrc";
import { peekProtectedMediaSrc } from "../utils/protectedMediaSrc";
import { protectedMediaImgProps } from "../utils/contentProtection";
import styles from "./ProtectedProductImage.module.css";

/** 1×1 transparent GIF — layout placeholder without a media path. */
const PLACEHOLDER_SRC =
  "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==";

type ProtectedProductImageProps = Omit<
  ImgHTMLAttributes<HTMLImageElement>,
  "src"
> & {
  /** Real media path (``/media/...``); not written to ``img.src`` when blob works. */
  src: string;
  /** Layout classes for the outer frame (grid cell, thumb size). */
  frameClassName?: string;
  /**
   * Skip the tall shimmer reservation (``min-height: 10rem``).
   * Use for 40–72px thumbs in lists/trays so the frame does not stretch.
   */
  compact?: boolean;
};

function initialAllowFetch(src: string, loading: string | undefined): boolean {
  return loading !== "lazy" || Boolean(peekProtectedMediaSrc(src));
}

/**
 * Product photo via session ``blob:`` URL so Inspect does not show ``/media/...``.
 *
 * Shows a soft shimmer while bytes resolve, then fades the photo in. Remounts
 * reuse the session blob cache without a blank flash.
 */
export function ProtectedProductImage({
  src,
  alt = "",
  className,
  frameClassName,
  compact = false,
  loading = "lazy",
  onLoad,
  ...rest
}: ProtectedProductImageProps) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [trackedSrc, setTrackedSrc] = useState(src);
  const [allowFetch, setAllowFetch] = useState(() =>
    initialAllowFetch(src, loading),
  );
  const [revealed, setRevealed] = useState(() =>
    Boolean(peekProtectedMediaSrc(src)),
  );

  // Reset reveal/fetch gates when the media path changes (render-time adjust).
  if (src !== trackedSrc) {
    setTrackedSrc(src);
    setAllowFetch(initialAllowFetch(src, loading));
    setRevealed(Boolean(peekProtectedMediaSrc(src)));
  }

  const displaySrc = useProtectedMediaSrc(allowFetch ? src : null);

  useEffect(() => {
    if (allowFetch || loading !== "lazy") {
      return;
    }
    const node = imgRef.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      setAllowFetch(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setAllowFetch(true);
          observer.disconnect();
        }
      },
      { rootMargin: "240px 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [allowFetch, loading, src]);

  const showShimmer = !revealed;
  const frameClass = [
    styles.frame,
    compact ? styles.frameCompact : null,
    frameClassName,
  ]
    .filter(Boolean)
    .join(" ");
  const mediaClass = [
    styles.media,
    revealed ? styles.mediaReady : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <span className={frameClass} data-ready={revealed ? "true" : "false"}>
      {showShimmer ? (
        <span className={styles.shimmer} aria-hidden="true" />
      ) : null}
      <img
        ref={imgRef}
        src={displaySrc ?? PLACEHOLDER_SRC}
        alt={alt}
        className={mediaClass}
        loading={loading}
        decoding="async"
        {...protectedMediaImgProps}
        {...rest}
        onLoad={(event) => {
          if (displaySrc) {
            setRevealed(true);
          }
          onLoad?.(event);
        }}
      />
    </span>
  );
}
