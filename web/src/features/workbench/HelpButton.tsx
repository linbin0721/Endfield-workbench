import { useState, type ReactNode } from "react";
import { Drawer } from "../../ui/Drawer/Drawer";
import { Button } from "../../ui/Button/Button";
import { InfoIcon } from "../../ui/icons";

/** "How to use" button opening a side panel with the examples and notes. */
export function HelpButton({ label, title, closeLabel, children }: {
  label: string;
  title: string;
  closeLabel: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return <Drawer side="right" open={open} onOpenChange={setOpen} title={title} closeLabel={closeLabel}
    trigger={<Button variant="secondary" size="sm" icon={<InfoIcon />}>{label}</Button>}>
    {children}
  </Drawer>;
}
