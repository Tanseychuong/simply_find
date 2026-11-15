import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

/*
  "light" | "dark" | "system". The class on <html> is first set by the inline
  script in index.html (no flash); this keeps it in sync afterwards.
*/
const ThemeContext = createContext(null);
const KEY = "sf-theme";

/*
  Dark mode is switched off for now: the site is always light and the toggle
  is hidden. The dark colours (index.css) and this code are kept; to bring it
  back, set this to true and `darkModeEnabled` in index.html's inline script.
*/
export const DARK_MODE_ENABLED = false;

function readSaved() {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export function ThemeProvider({ children }) {
  const [saved, setThemeState] = useState(readSaved);
  const theme = DARK_MODE_ENABLED ? saved : "light";

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const dark = theme === "dark" || (theme === "system" && media.matches);
      document.documentElement.classList.toggle("dark", dark);
    };
    apply();
    if (theme !== "system") return undefined;
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);

  const setTheme = useCallback((next) => {
    setThemeState(next);
    try {
      if (next === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, next);
    } catch {
      /* private mode: the choice lasts for this visit */
    }
  }, []);

  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside <ThemeProvider>");
  return ctx;
}
