import styles from "./Skeleton.module.css";

interface SkeletonProps {
  width?: string;
  height?: string;
  borderRadius?: string;
  className?: string;
  variant?: "shimmer" | "pulse" | "block";
}

export function Skeleton({
  width = "100%",
  height = "1em",
  borderRadius,
  className = "",
  variant = "shimmer",
}: SkeletonProps) {
  const variantClass =
    variant === "block"
      ? styles.block
      : variant === "pulse"
        ? `${styles.skeleton} ${styles.pulse}`
        : styles.skeleton;
  return (
    <span
      className={`${variantClass} ${className}`}
      style={{
        width,
        height,
        borderRadius,
        display: "inline-block",
      }}
      aria-hidden="true"
    />
  );
}
