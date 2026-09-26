import { useEffect } from "react";

const SELECTORS =
  'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

/**
 * Traps Tab focus within the container while `active`.
 * Restores focus to the previously focused element on cleanup.
 */
export function useFocusTrap(ref, active = true) {
  useEffect(() => {
    if (!active || !ref.current) return;
    const container = ref.current;
    const previouslyFocused = document.activeElement;

    const handleKey = (e) => {
      if (e.key === "Escape") {
        container.dispatchEvent(new CustomEvent("focustrap:escape", { bubbles: true }));
        return;
      }
      if (e.key !== "Tab") return;
      const focusables = Array.from(container.querySelectorAll(SELECTORS)).filter(
        (el) => el.offsetParent !== null
      );
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    container.addEventListener("keydown", handleKey);
    const first = container.querySelector(SELECTORS);
    if (first) first.focus();

    return () => {
      container.removeEventListener("keydown", handleKey);
      if (previouslyFocused && previouslyFocused.focus) previouslyFocused.focus();
    };
  }, [ref, active]);
}
