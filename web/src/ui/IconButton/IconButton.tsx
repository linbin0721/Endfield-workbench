import type { ComponentPropsWithRef, ReactNode } from "react";
import styles from "./IconButton.module.css";

type IconButtonProps = Omit<ComponentPropsWithRef<"button">, "children"> & {
  /** Accessible name; icon-only buttons have no visible text. */
  label: string;
  icon: ReactNode;
};

/** Round 44px icon-only button (close, theme switch). */
export function IconButton({ label, icon, className, type = "button", ...rest }: IconButtonProps) {
  return <button
    type={type}
    aria-label={label}
    title={label}
    className={[styles.button, className ?? ""].filter(Boolean).join(" ")}
    {...rest}
  >{icon}</button>;
}
