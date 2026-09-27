/**
 * Programmatic screen-reader announcements.
 * Usage: announce("وظیفه انجام شد") from anywhere after a state change.
 *
 * Lives in its own module so `components/LiveRegion.jsx` exports only a
 * component (see the Fast Refresh note in `hooks/useAuth.js`).
 */
export function announce(message, politeness = "polite") {
  window.dispatchEvent(
    new CustomEvent("hadi:announce", { detail: { message, politeness } })
  );
}
