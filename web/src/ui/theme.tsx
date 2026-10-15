import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { SurfaceScope, useSurface, type SurfaceName } from "./surface";

export type ThemeName = SurfaceName;

/** localStorage key; the inline script in index.html reads the same key before first paint. */
export const THEME_STORAGE_KEY = "ew-theme";
const DEFAULT_THEME: ThemeName = "light";

function readInitialTheme(): ThemeName {
  const preset = document.documentElement.dataset.surface;
  if (preset === "light" || preset === "dark") return preset;
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY) === "dark" ? "dark" : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

type ThemeContextValue = {
  theme: ThemeName;
  setTheme: (theme: ThemeName) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

/**
 * Site-wide light/dark theme (light by default). The choice is applied as
 * data-surface on <html>, so the page and every portal pick up the tokens,
 * and is remembered per browser when storage is available.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeName>(readInitialTheme);

  useEffect(() => {
    document.documentElement.dataset.surface = theme;
  }, [theme]);

  const setTheme = useCallback((next: ThemeName) => {
    // Applied right away so a view transition can capture the new theme.
    document.documentElement.dataset.surface = next;
    setThemeState(next);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // Private mode or blocked storage: the theme still applies for this visit.
    }
  }, []);

  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme]);
  return <ThemeContext.Provider value={value}>
    <SurfaceScope surface={theme}>{children}</SurfaceScope>
  </ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used inside <ThemeProvider>");
  return context;
}

/**
 * Site theme for page-level overlays (dialogs), ignoring local surfaces such as
 * the dark puzzle "screen". Falls back to the nearest surface without a provider.
 */
export function useSiteSurface(): SurfaceName {
  const context = useContext(ThemeContext);
  const local = useSurface();
  return context?.theme ?? local;
}
