import type { ReactNode } from "react";
import styles from "./PageHeader.module.css";

type PageHeaderProps = {
  title: ReactNode;
  /** Small uppercase label above the title, e.g. "PUZZLE SOLVER". */
  eyebrow?: ReactNode;
  children?: ReactNode;
};

/** "// Title" page heading with a barcode-like label strip. */
export function PageHeader({ title, eyebrow, children }: PageHeaderProps) {
  return <header className={styles.header}>
    {eyebrow
      ? <p className={styles.eyebrow}><span className={styles.code} aria-hidden="true" />{eyebrow}</p>
      : null}
    <h1 className={styles.title}><span className={styles.slashes} aria-hidden="true">//</span>{title}</h1>
    {children ? <div className={styles.body}>{children}</div> : null}
  </header>;
}
