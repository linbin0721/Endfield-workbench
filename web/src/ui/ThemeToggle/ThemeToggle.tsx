import { IconButton } from "../IconButton/IconButton";
import { MoonIcon, SunIcon } from "../icons";
import { useTheme } from "../theme";

type ThemeToggleProps = {
  /** Label for switching to dark, shown while the light theme is active. */
  toDarkLabel: string;
  toLightLabel: string;
};

/** Switches the site theme; the icon shows the theme you will switch to. */
export function ThemeToggle({ toDarkLabel, toLightLabel }: ThemeToggleProps) {
  const { theme, setTheme } = useTheme();
  const isDark = theme === "dark";
  return <IconButton
    label={isDark ? toLightLabel : toDarkLabel}
    icon={isDark ? <SunIcon /> : <MoonIcon />}
    onClick={() => setTheme(isDark ? "light" : "dark")}
  />;
}
