import * as RadixDialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";
import { IconButton } from "../IconButton/IconButton";
import { CloseIcon } from "../icons";
import { SurfaceScope } from "../surface";
import { useSiteSurface } from "../theme";
import styles from "./Drawer.module.css";

type DrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Element that opens the drawer; focus returns to it on close. */
  trigger: ReactNode;
  title: ReactNode;
  closeLabel: string;
  children: ReactNode;
  /** Edge the sheet slides in from (the mobile menu uses the left). */
  side?: "left" | "right";
};

/**
 * Modal side sheet sliding in from the left (the mobile menu) or the right. Built on the
 * Radix dialog, so focus is trapped while open and Escape closes it. Like the
 * dialog it follows the site theme and sets the surface on its portal content.
 */
export function Drawer({ open, onOpenChange, trigger, title, closeLabel, children, side = "left" }: DrawerProps) {
  const surface = useSiteSurface();
  return <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
    <RadixDialog.Trigger asChild>{trigger}</RadixDialog.Trigger>
    <RadixDialog.Portal>
      <RadixDialog.Overlay className={styles.overlay} />
      <RadixDialog.Content data-surface={surface} className={[styles.content, side === "right" ? styles.right : ""].filter(Boolean).join(" ")}
        aria-describedby={undefined}>
        <SurfaceScope surface={surface}>
          <div className={styles.header}>
            <RadixDialog.Title className={styles.title}>
              <span className={styles.slashes} aria-hidden="true">//</span>{title}
            </RadixDialog.Title>
            <RadixDialog.Close asChild><IconButton label={closeLabel} icon={<CloseIcon />} /></RadixDialog.Close>
          </div>
          <div className={styles.body}>{children}</div>
        </SurfaceScope>
      </RadixDialog.Content>
    </RadixDialog.Portal>
  </RadixDialog.Root>;
}
