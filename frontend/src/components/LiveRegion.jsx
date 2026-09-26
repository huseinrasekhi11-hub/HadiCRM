import { useEffect, useState } from "react";

/**
 * Programmatic screen-reader announcements.
 * Usage: announce("وظیفه انجام شد") from anywhere after a state change.
 */
export function announce(message, politeness = "polite") {
  window.dispatchEvent(
    new CustomEvent("hadi:announce", { detail: { message, politeness } })
  );
}

export default function LiveRegion() {
  const [polite, setPolite] = useState("");
  const [assertive, setAssertive] = useState("");

  useEffect(() => {
    const handler = (e) => {
      const { message, politeness } = e.detail || {};
      if (!message) return;
      if (politeness === "assertive") setAssertive(message);
      else setPolite(message);
    };
    window.addEventListener("hadi:announce", handler);
    return () => window.removeEventListener("hadi:announce", handler);
  }, []);

  return (
    <>
      <div aria-live="polite" aria-atomic="true" className="sr-only">{polite}</div>
      <div aria-live="assertive" aria-atomic="true" className="sr-only">{assertive}</div>
    </>
  );
}
