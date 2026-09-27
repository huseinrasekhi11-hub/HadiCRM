import { useEffect, useState, useMemo, useCallback } from "react";
import { ThemeContext } from "../hooks/useTheme";

const STORAGE_KEY = "hadiflow_theme";
// Kept in sync with the --bg-app token for each theme, so the browser chrome
// on mobile matches the page instead of showing a seam at the top.
const CHROME = { light: "#f6f8f9", dark: "#0c1216" };

function readInitial() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return saved === "dark";
  } catch {
    /* private mode */
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function ThemeProvider({ children }) {
  const [isDark, setIsDark] = useState(readInitial);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", isDark);
    try {
      localStorage.setItem(STORAGE_KEY, isDark ? "dark" : "light");
    } catch {
      /* ignore */
    }

    // Update the un-media'd theme-color so the address bar follows the app's
    // own setting rather than the OS preference.
    let meta = document.querySelector('meta[name="theme-color"]:not([media])');
    if (!meta) {
      meta = document.createElement("meta");
      meta.name = "theme-color";
      document.head.appendChild(meta);
    }
    meta.content = isDark ? CHROME.dark : CHROME.light;
  }, [isDark]);

  // If the user has never chosen explicitly, follow the system when it
  // changes — someone on an automatic night schedule should not have to
  // toggle this by hand at sunset.
  useEffect(() => {
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (e) => {
      let hasExplicit = false;
      try {
        hasExplicit = Boolean(localStorage.getItem(STORAGE_KEY));
      } catch {
        /* ignore */
      }
      if (!hasExplicit) setIsDark(e.matches);
    };
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  const toggleTheme = useCallback(() => setIsDark((v) => !v), []);

  const value = useMemo(() => ({ isDark, toggleTheme }), [isDark, toggleTheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
