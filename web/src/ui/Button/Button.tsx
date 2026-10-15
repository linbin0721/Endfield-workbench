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

export function buttonClassName({ variant = "primary", size = "md", block = false, className }: {
  variant?: ButtonVariant;
  size?: "md" | "sm";
  block?: boolean;
  className?: string;
} = {}): string {
  return [styles.button, styles[variant], styles[size], block ? styles.block : "", className ?? ""]
    .filter(Boolean)
    .join(" ");
}

/**
 * Inside of a capsule button, for links that must look like one
 * (`<Link className={buttonClassName()}><ButtonContent>…</ButtonContent></Link>`).
 */
export function ButtonContent({ icon, children }: { icon?: ReactNode; children: ReactNode }) {
  return <>
    <span className={styles.rule} aria-hidden="true" />
    <span className={styles.label}>{children}</span>
    <span className={styles.icon} aria-hidden="true">{icon ?? <ChevronRightIcon />}</span>
  </>;
}

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
  return <button type={type} className={buttonClassName({ variant, size, block, className })} disabled={disabled} {...rest}>
    {variant === "ghost"
      ? <span className={styles.label}>{children}</span>
      : <ButtonContent icon={disabled ? <BanIcon /> : icon}>{children}</ButtonContent>}
  </button>;
}
