import type { ComponentPropsWithRef, ReactNode } from "react";
import { BanIcon, ChevronRightIcon } from "../icons";
import styles from "./Button.module.css";

export type ButtonVariant = "primary" | "accent" | "secondary" | "ghost";

type ButtonProps = ComponentPropsWithRef<"button"> & {
  variant?: ButtonVariant;
  size?: "md" | "sm";
  /** Round trailing icon of capsule buttons; ignored by ghost buttons. */
  icon?: ReactNode;
  block?: boolean;
};

/**
 * Game-style capsule button: a short rule, the label, then a round icon.
 * Disabled buttons switch to an outlined state with a "not allowed" icon
 * instead of fading, so the reason stays readable.
 */
export function Button({
  variant = "primary",
  size = "md",
  icon,
  block = false,
  className,
  type = "button",
  disabled,
  children,
  ...rest
}: ButtonProps) {
  const classes = [styles.button, styles[variant], styles[size], block ? styles.block : "", className ?? ""]
    .filter(Boolean)
    .join(" ");
  const capsule = variant !== "ghost";
  return <button type={type} className={classes} disabled={disabled} {...rest}>
    {capsule ? <span className={styles.rule} aria-hidden="true" /> : null}
    <span className={styles.label}>{children}</span>
    {capsule
      ? <span className={styles.icon} aria-hidden="true">{disabled ? <BanIcon /> : icon ?? <ChevronRightIcon />}</span>
      : null}
  </button>;
}
