import type { ReactNode } from "react";
import styles from "./SuccessReveal.module.css";

type SuccessRevealProps = {
  title: ReactNode;
  detail?: ReactNode;
};

/**
 * Completion banner: a dark band opens from the centre, the title fades in and
 * a yellow line extends both ways (~0.55s, measured from the game). Purely
 * visual; mount it with a new `key` to replay. Announce results separately.
 */
export function SuccessReveal({ title, detail }: SuccessRevealProps) {
  return <div className={styles.reveal}>
    <span className={styles.band} aria-hidden="true" />
    <span className={styles.hairline} aria-hidden="true" />
    <p className={styles.title}>{title}</p>
    <span className={styles.underline} aria-hidden="true" />
    {detail ? <p className={styles.detail}>{detail}</p> : null}
  </div>;
}

type SuccessGlowProps = {
  /** Change to replay the glow (e.g. a solve counter); 0 or "" shows none. */
  playKey: number | string;
  children: ReactNode;
};

/** Short glow and outline flash around a finished board; layout is unaffected. */
export function SuccessGlow({ playKey, children }: SuccessGlowProps) {
  return <div className={styles.glowFrame}>
    {children}
    {playKey ? <span key={playKey} className={styles.glow} aria-hidden="true" /> : null}
  </div>;
}
