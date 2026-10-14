import type { ComponentPropsWithoutRef, ElementType } from "react";
import styles from "./Panel.module.css";

type PanelProps<T extends ElementType> = {
  as?: T;
  tone?: "default" | "strong";
  /** The small "+" corner marks used on game panels. */
  corners?: boolean;
} & Omit<ComponentPropsWithoutRef<T>, "as">;

export function Panel<T extends ElementType = "section">({
  as,
  tone = "default",
  corners = false,
  className,
  children,
  ...rest
}: PanelProps<T>) {
  const Component = (as ?? "section") as ElementType;
  const classes = [styles.panel, tone === "strong" ? styles.strong : "", className ?? ""].filter(Boolean).join(" ");
  return <Component className={classes} {...rest}>
    {corners
      ? <span className={styles.corners} aria-hidden="true"><i /><i /><i /><i /></span>
      : null}
    {children}
  </Component>;
}
