import { useEffect, useId, useState, type MouseEvent } from "react";
import { createPortal } from "react-dom";

import { ProtectedProductImage } from "./ProtectedProductImage";
import styles from "./ImageLightbox.module.css";

export interface LightboxImage {
  src: string;
  alt: string;
}

interface ImageLightboxProps {
  images: LightboxImage[];
  index: number;
  onClose: () => void;
  onIndexChange: (index: number) => void;
}

const ZOOM_SCALE = 2.5;

function ZoomablePhoto({ src, alt }: { src: string; alt: string }) {
  const [zoomed, setZoomed] = useState(false);
  const [origin, setOrigin] = useState({ x: 50, y: 50 });

  const toggleZoom = (event: MouseEvent<HTMLImageElement>) => {
    if (zoomed) {
      setZoomed(false);
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * 100;
    const y = ((event.clientY - rect.top) / rect.height) * 100;
    setOrigin({
      x: Math.min(100, Math.max(0, x)),
      y: Math.min(100, Math.max(0, y)),
    });
    setZoomed(true);
  };

  return (
    <>
      <ProtectedProductImage
        src={src}
        alt={alt}
        className={`${zoomed ? styles.imageZoomed : styles.image} u-protect-media`}
        style={
          zoomed
            ? {
                transformOrigin: `${origin.x}% ${origin.y}%`,
                transform: `scale(${ZOOM_SCALE})`,
              }
            : undefined
        }
        onClick={toggleZoom}
        loading="eager"
      />
      <p className={styles.hint}>
        {zoomed
          ? "Нажмите, чтобы уменьшить"
          : "Нажмите на фото, чтобы увеличить"}
      </p>
    </>
  );
}

/**
 * Full-viewport product photo viewer with click-to-zoom and gallery nav.
 *
 * Esc / backdrop / close button dismiss; ←/→ switch photos when several.
 */
export function ImageLightbox({
  images,
  index,
  onClose,
  onIndexChange,
}: ImageLightboxProps) {
  const titleId = useId();
  const safeIndex = Math.min(Math.max(index, 0), Math.max(images.length - 1, 0));
  const current = images[safeIndex];
  const multi = images.length > 1;

  useEffect(() => {
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (!multi) return;
      if (event.key === "ArrowLeft") {
        onIndexChange((safeIndex - 1 + images.length) % images.length);
      }
      if (event.key === "ArrowRight") {
        onIndexChange((safeIndex + 1) % images.length);
      }
    };

    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [images.length, multi, onClose, onIndexChange, safeIndex]);

  if (!current) return null;

  return createPortal(
    <div
      className={styles.backdrop}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      onClick={onClose}
    >
      <p id={titleId} className={styles.srOnly}>
        Просмотр фотографии
      </p>

      <button
        type="button"
        className={styles.close}
        aria-label="Закрыть"
        onClick={onClose}
      >
        ×
      </button>

      {multi ? (
        <>
          <button
            type="button"
            className={`${styles.nav} ${styles.navPrev}`}
            aria-label="Предыдущее фото"
            onClick={(event) => {
              event.stopPropagation();
              onIndexChange((safeIndex - 1 + images.length) % images.length);
            }}
          >
            ‹
          </button>
          <button
            type="button"
            className={`${styles.nav} ${styles.navNext}`}
            aria-label="Следующее фото"
            onClick={(event) => {
              event.stopPropagation();
              onIndexChange((safeIndex + 1) % images.length);
            }}
          >
            ›
          </button>
        </>
      ) : null}

      <div className={styles.stage} onClick={(event) => event.stopPropagation()}>
        <ZoomablePhoto
          key={safeIndex}
          src={current.src}
          alt={current.alt}
        />
        {multi ? (
          <p className={styles.hint}>{`${safeIndex + 1} / ${images.length}`}</p>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}
