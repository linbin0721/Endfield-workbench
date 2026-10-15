import styles from "./BrandMark.module.css";

/** Self-drawn site mark (not the game logo): a cut-corner plate with "//". */
export function BrandMark({ className }: { className?: string }) {
  return <svg
    className={[styles.mark, className ?? ""].filter(Boolean).join(" ")}
    viewBox="0 0 32 32"
    width="32"
    height="32"
    aria-hidden="true"
    focusable="false"
  >
    <path className={styles.plate} d="M2 2h20l8 8v20H2z" />
    <path className={styles.slashes} d="M10.5 23l5-14M16.5 23l5-14" />
  </svg>;
}
