import * as ToggleGroup from "@radix-ui/react-toggle-group";
import type { ReactNode } from "react";
import styles from "./SegmentedControl.module.css";

export type Segment = {
  value: string;
  label: ReactNode;
  disabled?: boolean;
};

type SegmentedControlProps = {
  /** Empty string means nothing is selected yet (e.g. the puzzles' initial input mode). */
  value: string;
  onValueChange: (value: string) => void;
  segments: Segment[];
  "aria-label": string;
  size?: "md" | "sm";
  block?: boolean;
  className?: string;
};

/**
 * Single-choice capsule switch. Arrow keys only move focus; Enter, Space or a
 * click selects. Clicking the active segment keeps it selected rather than
 * clearing the choice, so callers never receive an accidental empty value.
 */
export function SegmentedControl({
  value,
  onValueChange,
  segments,
  size = "md",
  block = false,
  className,
  ...aria
}: SegmentedControlProps) {
  return <ToggleGroup.Root
    type="single"
    value={value}
    onValueChange={(next) => { if (next) onValueChange(next); }}
    aria-label={aria["aria-label"]}
    className={[styles.root, size === "sm" ? styles.sm : "", block ? styles.block : "", className ?? ""]
      .filter(Boolean)
      .join(" ")}
  >
    {segments.map((segment) => <ToggleGroup.Item
      key={segment.value}
      value={segment.value}
      disabled={segment.disabled}
      className={styles.item}
    >{segment.label}</ToggleGroup.Item>)}
  </ToggleGroup.Root>;
}
