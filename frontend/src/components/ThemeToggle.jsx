import { Sun, Moon } from "lucide-react";
import { useTheme } from "../hooks/useTheme";

export default function ThemeToggle() {
  const { isDark, toggleTheme } = useTheme();

  return (
    <button 
      onClick={toggleTheme} 
      className="theme-toggle-btn"
      aria-label="تغییر تم"
      title={isDark ? "تم روشن" : "تم تاریک"}
    >
      {isDark ? <Sun size={18} strokeWidth={2.2} /> : <Moon size={18} strokeWidth={2.2} />}
    </button>
  );
}
