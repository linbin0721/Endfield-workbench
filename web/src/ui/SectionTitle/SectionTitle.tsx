import type { ReactNode } from "react";
import styles from "./SectionTitle.module.css";

type SectionTitleProps = {
  children: ReactNode;
  level?: 2 | 3;
  /** Optional content on the right (a count, a small action). */
  aside?: ReactNode;
  id?: string;
};

/** Yellow bar, title, then a hairline running to the edge, as on game panels. */
export function SectionTitle({ children, level = 2, aside, id }: SectionTitleProps) {
  const Heading = level === 2 ? "h2" : "h3";
  return <div className={styles.row}>
    <Heading id={id} className={[styles.title, level === 3 ? styles.small : ""].filter(Boolean).join(" ")}>
      {children}
    </Heading>
    <span className={styles.rule} aria-hidden="true" />
    {aside ? <div className={styles.aside}>{aside}</div> : null}
  </div>;
}
