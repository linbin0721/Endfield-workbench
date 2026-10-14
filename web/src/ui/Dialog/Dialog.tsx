import * as RadixDialog from "@radix-ui/react-dialog";
import type { ComponentProps, ReactNode } from "react";
import { Button } from "../Button/Button";
import { CloseIcon } from "../icons";
import { Surface, SurfaceScope } from "../surface";
import styles from "./Dialog.module.css";

type DialogProps = {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Element that opens the dialog; focus returns to it on close. */
  trigger?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  closeLabel: string;
  children?: ReactNode;
  /** Actions shown on the dark strip at the bottom. */
  footer?: ReactNode;
};

/**
 * Game-style modal: a light panel with a "// title" header and a dark action
 * strip. It always uses the light surface regardless of the page, and sets it
 * explicitly because the content is portalled to <body>.
 */
export function Dialog({ open, onOpenChange, trigger, title, description, closeLabel, children, footer }: DialogProps) {
  return <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
    {trigger ? <RadixDialog.Trigger asChild>{trigger}</RadixDialog.Trigger> : null}
    <RadixDialog.Portal>
      <RadixDialog.Overlay className={styles.overlay} />
      <RadixDialog.Content data-surface="light" className={styles.content}>
        <SurfaceScope surface="light">
          <div className={styles.header}>
            <RadixDialog.Title className={styles.title}>
              <span className={styles.slashes} aria-hidden="true">//</span>{title}
            </RadixDialog.Title>
            <RadixDialog.Close className={styles.close} aria-label={closeLabel}><CloseIcon /></RadixDialog.Close>
          </div>
          {description
            ? <RadixDialog.Description className={styles.description}>{description}</RadixDialog.Description>
            : null}
          {children ? <div className={styles.body}>{children}</div> : null}
          {footer ? <Surface surface="dark" className={styles.footer}>{footer}</Surface> : null}
        </SurfaceScope>
      </RadixDialog.Content>
    </RadixDialog.Portal>
  </RadixDialog.Root>;
}

/** Footer action that closes the dialog (focus then returns to the trigger). */
function DialogCloseButton(props: ComponentProps<typeof Button>) {
  return <RadixDialog.Close asChild><Button {...props} /></RadixDialog.Close>;
}

Dialog.CloseButton = DialogCloseButton;
