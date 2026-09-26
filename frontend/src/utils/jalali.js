/**
 * ============================================================
 * Jalali (Shamsi / Solar Hijri) calendar core
 * ------------------------------------------------------------
 * Conversion between the Jalali and Gregorian calendars, plus
 * the parsing and serialising helpers the date picker needs.
 *
 * Gregorian is used *only* as the wire format — the API speaks
 * ISO 8601 and that cannot change. Nothing here is ever shown
 * to a user in Gregorian form.
 *
 * Algorithm follows the standard Birashk/Borkowski arithmetic
 * used by jalaali-js, accurate for jy 1178–1633 (≈1800–2255).
 * ============================================================
 */

const div = (a, b) => ~~(a / b);
const mod = (a, b) => a - ~~(a / b) * b;

// Jalali leap-year breakpoints.
const BREAKS = [
  -61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181,
  1210, 1635, 1701, 1866, 2328, 3167,
];

function jalCal(jy) {
  const bl = BREAKS.length;
  const gy = jy + 621;
  let leapJ = -14;
  let jp = BREAKS[0];
  let jm;
  let jump = 0;

  if (jy < jp || jy >= BREAKS[bl - 1]) throw new RangeError(`Invalid Jalali year ${jy}`);

  for (let i = 1; i < bl; i += 1) {
    jm = BREAKS[i];
    jump = jm - jp;
    if (jy < jm) break;
    leapJ = leapJ + div(jump, 33) * 8 + div(mod(jump, 33), 4);
    jp = jm;
  }
  let n = jy - jp;

  leapJ = leapJ + div(n, 33) * 8 + div(mod(n, 33) + 3, 4);
  if (mod(jump, 33) === 4 && jump - n === 4) leapJ += 1;

  const leapG = div(gy, 4) - div((div(gy, 100) + 1) * 3, 4) - 150;
  const march = 20 + leapJ - leapG;

  if (jump - n < 6) n = n - jump + div(jump + 4, 33) * 33;
  let leap = mod(mod(n + 1, 33) - 1, 4);
  if (leap === -1) leap = 4;

  return { leap, gy, march };
}

function g2d(gy, gm, gd) {
  let d =
    div((gy + div(gm - 8, 6) + 100100) * 1461, 4) +
    div(153 * mod(gm + 9, 12) + 2, 5) +
    gd -
    34840408;
  d = d - div(div(gy + 100100 + div(gm - 8, 6), 100) * 3, 4) + 752;
  return d;
}

function d2g(jdn) {
  let j = 4 * jdn + 139361631;
  j = j + div(div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908;
  const i = div(mod(j, 1461), 4) * 5 + 308;
  const gd = div(mod(i, 153), 5) + 1;
  const gm = mod(div(i, 153), 12) + 1;
  const gy = div(j, 1461) - 100100 + div(8 - gm, 6);
  return { gy, gm, gd };
}

function j2d(jy, jm, jd) {
  const r = jalCal(jy);
  return g2d(r.gy, 3, r.march) + (jm - 1) * 31 - div(jm, 7) * (jm - 7) + jd - 1;
}

function d2j(jdn) {
  const gy0 = d2g(jdn).gy;
  let jy = gy0 - 621;
  const r = jalCal(jy);
  const jdn1f = g2d(gy0, 3, r.march);
  let k = jdn - jdn1f;

  if (k >= 0) {
    if (k <= 185) return { jy, jm: 1 + div(k, 31), jd: mod(k, 31) + 1 };
    k -= 186;
  } else {
    jy -= 1;
    k += 179;
    if (r.leap === 1) k += 1;
  }
  return { jy, jm: 7 + div(k, 30), jd: mod(k, 30) + 1 };
}

/* ---------------------------------------------------------- */
/* Public conversion API                                       */
/* ---------------------------------------------------------- */

export function isLeapJalaliYear(jy) {
  return jalCal(jy).leap === 0;
}

/** Days in a given Jalali month: 31 for Farvardin–Shahrivar, 30 for Mehr–Bahman, 29/30 for Esfand. */
export function jalaliMonthLength(jy, jm) {
  if (jm <= 6) return 31;
  if (jm <= 11) return 30;
  return isLeapJalaliYear(jy) ? 30 : 29;
}

export function toJalali(gy, gm, gd) {
  return d2j(g2d(gy, gm, gd));
}

export function toGregorian(jy, jm, jd) {
  return d2g(j2d(jy, jm, jd));
}

/** A JS Date (local time) -> {jy, jm, jd}. */
export function dateToJalali(date) {
  return toJalali(date.getFullYear(), date.getMonth() + 1, date.getDate());
}

/** {jy, jm, jd} (+ optional clock) -> a JS Date in local time. */
export function jalaliToDate(jy, jm, jd, hours = 0, minutes = 0) {
  const { gy, gm, gd } = toGregorian(jy, jm, jd);
  return new Date(gy, gm - 1, gd, hours, minutes, 0, 0);
}

/* ---------------------------------------------------------- */
/* Names & digits                                              */
/* ---------------------------------------------------------- */

export const JALALI_MONTHS = [
  "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
  "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
];

/** Weekday labels, Saturday first — the Iranian week starts on Saturday. */
export const JALALI_WEEKDAYS = ["ش", "ی", "د", "س", "چ", "پ", "ج"];
export const JALALI_WEEKDAYS_FULL = [
  "شنبه", "یک‌شنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه",
];

const FA_DIGITS = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];

/** Latin digits -> Persian digits, leaving everything else alone. */
export const toFaDigits = (input) =>
  String(input).replace(/[0-9]/g, (d) => FA_DIGITS[Number(d)]);

/** Persian or Arabic-Indic digits -> Latin, so typed input can be parsed. */
export const toLatinDigits = (input) =>
  String(input)
    .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0))
    .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660));

const pad2 = (n) => String(n).padStart(2, "0");

/**
 * Column index (0 = Saturday) of the first day of a Jalali month.
 * JS getDay() is Sunday-based, so it is rotated by one.
 */
export function jalaliMonthStartColumn(jy, jm) {
  return (jalaliToDate(jy, jm, 1).getDay() + 1) % 7;
}

/* ---------------------------------------------------------- */
/* Input-value serialisation                                   */
/* ---------------------------------------------------------- */
/*
 * Form state stays on the same `YYYY-MM-DD` / `YYYY-MM-DDTHH:mm`
 * local-Gregorian strings the native inputs produced, so every
 * submit handler downstream keeps working untouched. Only what
 * the user sees and clicks is Jalali.
 */

/** Parse a form value into { jy, jm, jd, hours, minutes } or null. */
export function parseInputValue(value) {
  if (!value) return null;
  const m = String(value).match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/);
  if (!m) return null;
  const [, y, mo, d, h, mi] = m;
  const gy = Number(y);
  const gm = Number(mo);
  const gd = Number(d);
  if (gm < 1 || gm > 12 || gd < 1 || gd > 31) return null;
  try {
    const { jy, jm, jd } = toJalali(gy, gm, gd);
    return { jy, jm, jd, hours: h ? Number(h) : 0, minutes: mi ? Number(mi) : 0 };
  } catch {
    return null;
  }
}

/** Build a form value from Jalali parts. */
export function toInputValue({ jy, jm, jd, hours = 0, minutes = 0 }, withTime) {
  const { gy, gm, gd } = toGregorian(jy, jm, jd);
  const date = `${gy}-${pad2(gm)}-${pad2(gd)}`;
  return withTime ? `${date}T${pad2(hours)}:${pad2(minutes)}` : date;
}

/** A Date -> form value, for "today"/"tomorrow" style shortcuts. */
export function dateToInputValue(date, withTime) {
  const v = `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
  return withTime ? `${v}T${pad2(date.getHours())}:${pad2(date.getMinutes())}` : v;
}

/* ---------------------------------------------------------- */
/* Display                                                     */
/* ---------------------------------------------------------- */

/** Form value -> «۲۸ شهریور ۱۴۰۵» (plus «، ۱۵:۳۰» when withTime). */
export function formatInputValue(value, withTime) {
  const p = parseInputValue(value);
  if (!p) return "";
  const base = `${toFaDigits(p.jd)} ${JALALI_MONTHS[p.jm - 1]} ${toFaDigits(p.jy)}`;
  if (!withTime) return base;
  return `${base}، ${toFaDigits(pad2(p.hours))}:${toFaDigits(pad2(p.minutes))}`;
}

/** Form value -> «شنبه ۲۸ شهریور ۱۴۰۵». */
export function formatInputValueLong(value) {
  const p = parseInputValue(value);
  if (!p) return "";
  const weekday = JALALI_WEEKDAYS_FULL[(jalaliToDate(p.jy, p.jm, p.jd).getDay() + 1) % 7];
  return `${weekday} ${toFaDigits(p.jd)} ${JALALI_MONTHS[p.jm - 1]} ${toFaDigits(p.jy)}`;
}

/** Today as Jalali parts. */
export function todayJalaliParts() {
  return dateToJalali(new Date());
}

/** True when the given Jalali date is today. */
export function isJalaliToday(jy, jm, jd) {
  const t = todayJalaliParts();
  return t.jy === jy && t.jm === jm && t.jd === jd;
}
