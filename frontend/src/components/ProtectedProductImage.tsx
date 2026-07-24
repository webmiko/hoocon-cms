import {
  useEffect,
  useRef,
  useState,
  type ImgHTMLAttributes,
} from "react";

import { useProtectedMediaSrc } from "../hooks/useProtectedMediaSrc";
import { protectedMediaImgProps } from "../utils/contentProtection";

/** 1×1 transparent GIF — layout placeholder without a media path. */
const PLACEHOLDER_SRC =
  "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==";

type ProtectedProductImageProps = Omit<
  ImgHTMLAttributes<HTMLImageElement>,
  "src"
> & {
  /** Real media path (``/media/...``); not written to ``img.src`` when blob works. */
  src: string;
};

/**
 * Product photo via session ``blob:`` URL so Inspect does not show ``/media/...``.
 *
 * Keeps contentProtection drag/context-menu guards. ``loading="lazy"`` defers the
 * fetch until near the viewport.
 */
export function ProtectedProductImage({
  src,
  alt = "",
  className,
  loading = "lazy",
  ...rest
}: ProtectedProductImageProps) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [allowFetch, setAllowFetch] = useState(loading !== "lazy");
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
  }, [allowFetch, loading]);

  return (
    <img
      ref={imgRef}
      src={displaySrc ?? PLACEHOLDER_SRC}
      alt={alt}
      className={className}
      loading={loading}
      decoding="async"
      {...protectedMediaImgProps}
      {...rest}
    />
  );
}
