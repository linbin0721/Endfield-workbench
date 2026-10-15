import { flushSync } from "react-dom";
import { IconButton } from "../IconButton/IconButton";
import { MoonIcon, SunIcon } from "../icons";
import { useTheme, type ThemeName } from "../theme";

type ThemeToggleProps = {
  /** Label for switching to dark, shown while the light theme is active. */
  toDarkLabel: string;
  toLightLabel: string;
};

type TransitionDocument = Document & { startViewTransition?: (update: () => void) => unknown };

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Switches the site theme; the icon shows the theme you will switch to. Where
 * view transitions exist the new theme wipes in (see base.css); otherwise, and
 * with reduced motion, it switches at once.
 */
export function ThemeToggle({ toDarkLabel, toLightLabel }: ThemeToggleProps) {
  const { theme, setTheme } = useTheme();
  const isDark = theme === "dark";
  const switchTo = (next: ThemeName) => {
    const doc = document as TransitionDocument;
    if (!doc.startViewTransition || prefersReducedMotion()) {
      setTheme(next);
      return;
    }
    doc.startViewTransition(() => flushSync(() => setTheme(next)));
  };
  return <IconButton
    label={isDark ? toLightLabel : toDarkLabel}
    icon={isDark ? <SunIcon /> : <MoonIcon />}
    onClick={() => switchTo(isDark ? "light" : "dark")}
  />;
}
