import { useEffect, type ReactNode } from "react";
import styles from "./Toast.module.css";

type ToastProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
  /** Auto-dismiss delay in ms; 0 keeps it until closed. */
  duration?: number;
};

/**
 * Short top-centre message strip ("所需材料不足" in the game). The live region
 * stays mounted so screen readers announce each new message.
 */
export function Toast({ open, onOpenChange, children, duration = 2400 }: ToastProps) {
  useEffect(() => {
    if (!open || duration <= 0) return;
    const timer = window.setTimeout(() => onOpenChange(false), duration);
    return () => window.clearTimeout(timer);
  }, [open, duration, onOpenChange]);

  return <div className={styles.region} role="status" aria-live="polite">
    {open ? <div className={styles.toast}>{children}</div> : null}
  </div>;
}
