/**
 * Persian number/rial formatting helpers.
 *
 * They used to be exported from `components/charts/Charts.jsx`. Mixing
 * non-component exports into a component module disables Fast Refresh for
 * that file (the whole module falls back to a full reload), and it forced
 * pages that only needed a formatter to import the entire chart library.
 */

/** Persian-formatted integer, e.g. 12345 -> "۱۲٬۳۴۵". */
export const fmtNum = (n) => (Number(n) || 0).toLocaleString("fa-IR");

/** Compact rial amounts — "میلیارد" / "میلیون" — for axis labels and chips. */
export function fmtCompactRial(n) {
  const v = Number(n) || 0;
  if (v >= 1_000_000_000)
    return `${(v / 1_000_000_000).toLocaleString("fa-IR", { maximumFractionDigits: 1 })} میلیارد`;
  if (v >= 1_000_000)
    return `${(v / 1_000_000).toLocaleString("fa-IR", { maximumFractionDigits: 1 })} میلیون`;
  return v.toLocaleString("fa-IR");
}

/** Full amount with the currency word. */
export const fmtRial = (n) => `${fmtNum(n)} ریال`;
