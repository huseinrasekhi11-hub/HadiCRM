import { useEffect, useRef } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]),' +
  'select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Standard dialog behaviour, applied once instead of re-implemented per modal.
 *
 * Every modal in this app previously opened as a plain div: Escape did
 * nothing, Tab walked straight out into the page behind the backdrop, the
 * body kept scrolling under the overlay, and on close the keyboard focus was
 * dropped at the top of the document. This restores all four.
 *
 * @param {() => void} onClose  called on Escape
 * @param {boolean}    active
 * @returns {React.RefObject} attach to the dialog element
 */
export function useModalBehavior(onClose, active = true) {
  const ref = useRef(null);
  // Held in a ref so a new handler identity on each render does not tear down
  // and rebuild the listener — which would drop and re-apply the scroll lock
  // mid-interaction. Written in an effect rather than during render, since
  // mutating a ref while rendering is not safe under concurrent React.
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!active) return;
    const node = ref.current;
    const previouslyFocused = document.activeElement;

    // --- Scroll lock -----------------------------------------------------
    // Compensating for the scrollbar width stops the page behind the overlay
    // from jumping sideways the moment a modal opens.
    const scrollBarWidth = window.innerWidth - document.documentElement.clientWidth;
    const { overflow, paddingInlineEnd } = document.body.style;
    document.body.style.overflow = "hidden";
    if (scrollBarWidth > 0) document.body.style.paddingInlineEnd = `${scrollBarWidth}px`;

    // --- Initial focus ---------------------------------------------------
    // Prefer the first real input; fall back to the dialog itself so screen
    // readers announce the title rather than landing on "Cancel".
    const focusFirst = () => {
      if (!node) return;
      const target =
        node.querySelector("[data-autofocus]") ||
        node.querySelector("input:not([type=hidden]), textarea, select") ||
        node.querySelector(FOCUSABLE);
      if (target) target.focus({ preventScroll: true });
    };
    const raf = requestAnimationFrame(focusFirst);

    // --- Keyboard --------------------------------------------------------
    const onKeyDown = (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        closeRef.current?.();
        return;
      }
      if (e.key !== "Tab" || !node) return;

      const items = Array.from(node.querySelectorAll(FOCUSABLE)).filter(
        (el) => el.offsetParent !== null || el === document.activeElement
      );
      if (!items.length) return;

      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);

    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = overflow;
      document.body.style.paddingInlineEnd = paddingInlineEnd;
      if (previouslyFocused?.focus) previouslyFocused.focus({ preventScroll: true });
    };
  }, [active]);

  return ref;
}

export default useModalBehavior;
