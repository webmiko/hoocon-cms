import {
  useEffect,
  useRef,
  useState,
  type ImgHTMLAttributes,
} from "react";

import { protectedMediaImgProps } from "../utils/contentProtection";
import styles from "./ProtectedProductImage.module.css";

type ProtectedProductImageProps = Omit<
  ImgHTMLAttributes<HTMLImageElement>,
  "src"
> & {
  /** Same-origin media path (``/media/...``). */
  src: string;
  /** Layout classes for the outer frame (grid cell, thumb size). */
  frameClassName?: string;
  /**
   * Skip the tall shimmer reservation (``min-height: 10rem``).
   * Use for 40–72px thumbs in lists/trays so the frame does not stretch.
   */
  compact?: boolean;
};

/**
 * Product photo with a soft shimmer until the file paints.
 *
 * ``img.src`` is the real ``/media/...`` URL so the browser can cache, lazy-load,
 * and decode natively. A former ``blob:`` fetch hid the path in Inspect but
 * delayed catalog paint and was trivial to bypass.
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
  const [revealed, setRevealed] = useState(false);

  if (src !== trackedSrc) {
    setTrackedSrc(src);
    setRevealed(false);
  }

  useEffect(() => {
    const img = imgRef.current;
    if (img?.complete && img.naturalWidth > 0) {
      setRevealed(true);
    }
  }, [src]);

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
    <span
      className={frameClass}
      data-ready={revealed ? "true" : "false"}
    >
      {showShimmer ? (
        <span className={styles.shimmer} aria-hidden="true" />
      ) : null}
      <img
        ref={imgRef}
        src={src}
        alt={alt}
        className={mediaClass}
        loading={loading}
        decoding="async"
        {...protectedMediaImgProps}
        {...rest}
        onLoad={(event) => {
          setRevealed(true);
          onLoad?.(event);
        }}
        onError={(event) => {
          setRevealed(true);
          rest.onError?.(event);
        }}
      />
    </span>
  );
}
