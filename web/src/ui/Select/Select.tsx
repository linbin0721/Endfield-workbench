import * as RadixSelect from "@radix-ui/react-select";
import type { ReactNode } from "react";
import { CheckIcon, ChevronDownIcon } from "../icons";
import { useSurface } from "../surface";
import styles from "./Select.module.css";

export type SelectOption = {
  value: string;
  label: ReactNode;
  /** Plain-text label for type-ahead when `label` is not a string. */
  textValue?: string;
  disabled?: boolean;
  /** Trailing marker such as a warning icon. */
  adornment?: ReactNode;
};

type SelectProps = {
  value: string | undefined;
  onValueChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: ReactNode;
  /** Accessible name when no visible <label> points at `id`. */
  "aria-label"?: string;
  id?: string;
  name?: string;
  disabled?: boolean;
  size?: "md" | "sm";
  /** Icon before the value inside the trigger. */
  leading?: ReactNode;
  className?: string;
};

export function Select({
  value,
  onValueChange,
  options,
  placeholder,
  id,
  name,
  disabled,
  size = "md",
  leading,
  className,
  ...aria
}: SelectProps) {
  const surface = useSurface();
  return <RadixSelect.Root value={value} onValueChange={onValueChange} disabled={disabled} name={name}>
    <RadixSelect.Trigger
      id={id}
      aria-label={aria["aria-label"]}
      className={[styles.trigger, size === "sm" ? styles.sm : "", className ?? ""].filter(Boolean).join(" ")}
    >
      {leading ? <span className={styles.leading} aria-hidden="true">{leading}</span> : null}
      <span className={styles.value}><RadixSelect.Value placeholder={placeholder} /></span>
      <RadixSelect.Icon className={styles.chevron}><ChevronDownIcon /></RadixSelect.Icon>
    </RadixSelect.Trigger>
    <RadixSelect.Portal>
      {/* Portal content lives under <body>, so it receives the surface explicitly. */}
      <RadixSelect.Content data-surface={surface} className={styles.content} position="popper" sideOffset={6}>
        <RadixSelect.Viewport className={styles.viewport}>
          {options.map((option) => <RadixSelect.Item
            key={option.value}
            value={option.value}
            disabled={option.disabled}
            textValue={option.textValue}
            className={styles.item}
          >
            <RadixSelect.ItemText>{option.label}</RadixSelect.ItemText>
            {option.adornment ? <span className={styles.adornment} aria-hidden="true">{option.adornment}</span> : null}
            <RadixSelect.ItemIndicator className={styles.indicator}><CheckIcon /></RadixSelect.ItemIndicator>
          </RadixSelect.Item>)}
        </RadixSelect.Viewport>
      </RadixSelect.Content>
    </RadixSelect.Portal>
  </RadixSelect.Root>;
}
