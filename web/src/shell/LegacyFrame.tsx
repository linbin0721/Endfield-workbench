import type { ReactNode } from "react";
import styles from "./LegacyFrame.module.css";

/**
 * Dark "work screen" around a tool page that still uses the pre-redesign
 * styles. It stays dark in both themes until the page is migrated (B2/B3);
 * `.legacy-page` is the scope of the old element rules in styles.css.
 */
export function LegacyFrame({ children }: { children: ReactNode }) {
  return <div className={styles.frame}>
    <span className={styles.corners} aria-hidden="true"><i /><i /><i /><i /></span>
    <div className="legacy-page">{children}</div>
  </div>;
}
