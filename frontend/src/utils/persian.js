/**
 * ============================================================
 * Persian / Jalali Formatting Utilities
 * ------------------------------------------------------------
 * Single source of truth for all date, time, number, and
 * currency formatting in the Persian (Jalali) calendar.
 *
 * Every formatter uses the explicit `-u-ca-persian` Unicode
 * calendar extension so rendering is identical across browsers
 * and never silently falls back to Gregorian.
 * ============================================================
 */

/* ---------- Jalali calendar formatters (explicit) ---------- */

const jalaliDateFmt = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  dateStyle: "medium",
});
const jalaliDateTimeFmt = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  dateStyle: "medium",
  timeStyle: "short",
});
const jalaliTimeFmt = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  hour: "2-digit",
  minute: "2-digit",
});
const jalaliLongDateFmt = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  dateStyle: "full",
});
const jalaliMonthDayFmt = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  month: "long",
  day: "numeric",
});

function safeFormat(fmt, iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    return fmt.format(d);
  } catch {
    return "—";
  }
}

/** Jalali date, e.g. «۱۰ مرداد ۱۴۰۵» */
export const formatDate = (iso) => safeFormat(jalaliDateFmt, iso);

/** Jalali date + time, e.g. «۱۰ مرداد ۱۴۰۵، ۱۵:۳۰» */
export const formatDateTime = (iso) => safeFormat(jalaliDateTimeFmt, iso);

/** Time only, e.g. «۱۵:۳۰» */
export const formatTime = (iso) => safeFormat(jalaliTimeFmt, iso);

/** Full Jalali date with weekday, e.g. «شنبه ۱۰ مرداد ۱۴۰۵» */
export const formatLongDate = (iso) => safeFormat(jalaliLongDateFmt, iso);

/** Month + day, e.g. «۱۰ مرداد» */
export const formatMonthDay = (iso) => safeFormat(jalaliMonthDayFmt, iso);

/** Today's Jalali date, for dashboard greetings. */
export const todayJalali = () => jalaliLongDateFmt.format(new Date());

/* ---------- Number & currency (Persian digits) ---------- */

/** Integer with Persian digit grouping, e.g. ۱۲۳٬۴۵۶ */
export function formatNumber(num) {
  if (num == null || Number.isNaN(Number(num))) return "—";
  return Number(num).toLocaleString("fa-IR");
}

/** Rial amount with Persian digits, e.g. «۱۲۳٬۴۵۶ ریال» */
export function formatRial(amount) {
  if (amount == null || Number.isNaN(Number(amount))) return "—";
  return `${Number(amount).toLocaleString("fa-IR")} ریال`;
}

/**
 * Compact Rial for charts / dashboard axes.
 * Large values collapse to میلیون / میلیارد for readability.
 */
export function formatCompactRial(amount) {
  if (amount == null || Number.isNaN(Number(amount))) return "—";
  const num = Number(amount);
  if (num >= 1_000_000_000) {
    return `${(num / 1_000_000_000).toLocaleString("fa-IR", { maximumFractionDigits: 1 })} میلیارد`;
  }
  if (num >= 1_000_000) {
    return `${(num / 1_000_000).toLocaleString("fa-IR", { maximumFractionDigits: 1 })} میلیون`;
  }
  return num.toLocaleString("fa-IR");
}

/* ---------- Relative time (natural Persian) ---------- */

/**
 * Relative time vs. now, for follow-ups and due dates.
 * Returns { text, overdue } so callers can style the overdue state.
 */
export function formatRelativeTime(iso) {
  if (!iso) return null;
  const target = new Date(iso).getTime();
  if (Number.isNaN(target)) return null;
  const diffMs = target - Date.now();
  const overdue = diffMs < 0;
  const absHours = Math.abs(diffMs) / 3600000;
  const absDays = absHours / 24;

  let text;
  if (absHours < 1) {
    text = overdue ? "دقایقی پیش" : "کمتر از ۱ ساعت دیگر";
  } else if (absHours < 24) {
    const h = Math.round(absHours).toLocaleString("fa-IR");
    text = `${h} ساعت ${overdue ? "پیش" : "دیگر"}`;
  } else if (absDays < 30) {
    const d = Math.round(absDays).toLocaleString("fa-IR");
    text = `${d} روز ${overdue ? "پیش" : "دیگر"}`;
  } else {
    const m = Math.round(absDays / 30).toLocaleString("fa-IR");
    text = `${m} ماه ${overdue ? "پیش" : "دیگر"}`;
  }
  return { text, overdue };
}

/**
 * "Time ago" for notification feeds and history timestamps.
 * Always past tense.
 */
export function formatTimeAgo(iso) {
  if (!iso) return "";
  const diffMs = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(diffMs)) return "";
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "همین الان";
  if (mins < 60) return `${mins.toLocaleString("fa-IR")} دقیقه پیش`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours.toLocaleString("fa-IR")} ساعت پیش`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days.toLocaleString("fa-IR")} روز پیش`;
  const months = Math.floor(days / 30);
  return `${months.toLocaleString("fa-IR")} ماه پیش`;
}
