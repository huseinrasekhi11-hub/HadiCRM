import { useEffect, useMemo, useRef, useState } from "react";
import { CalendarDays, ChevronRight, ChevronLeft, Clock, X } from "lucide-react";
import {
  JALALI_MONTHS, JALALI_WEEKDAYS,
  jalaliMonthLength, jalaliMonthStartColumn,
  parseInputValue, toInputValue, formatInputValue,
  todayJalaliParts, isJalaliToday, toFaDigits, dateToInputValue,
} from "../utils/jalali";
import "./JalaliDatePicker.css";

/**
 * Shamsi (Jalali) date / date-time picker.
 *
 * Replaces the native <input type="date"> and <input type="datetime-local">
 * controls, which always render a Gregorian calendar and cannot be localised.
 *
 * The `value` contract is deliberately unchanged from the native inputs —
 * "YYYY-MM-DD" or "YYYY-MM-DDTHH:mm" in local time — so every submit handler
 * downstream keeps working. Only what the user reads and clicks is Shamsi.
 */
export default function JalaliDatePicker({
  value,
  onChange,
  withTime = false,
  required = false,
  disabled = false,
  clearable = false,
  placeholder = "انتخاب تاریخ",
  id,
  className = "",
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const panelRef = useRef(null);

  const parsed = useMemo(() => parseInputValue(value), [value]);
  const today = useMemo(() => todayJalaliParts(), []);

  // The month on screen. Follows the selected value, and falls back to the
  // current month when nothing is selected yet.
  const [view, setView] = useState(() => ({
    jy: parsed?.jy ?? today.jy,
    jm: parsed?.jm ?? today.jm,
  }));

  // The on-screen month follows the selected value. This is adjusted during
  // render (React's documented "adjust state on prop change" pattern) rather
  // than in an effect, which would commit one render showing the previous
  // month before switching.
  const [lastValue, setLastValue] = useState(value);
  if (lastValue !== value) {
    setLastValue(value);
    if (parsed) setView({ jy: parsed.jy, jm: parsed.jm });
  }

  /* --- Dismiss on outside click or Escape --- */
  useEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey, true);
    };
  }, [open]);

  /* --- Month grid --- */
  const grid = useMemo(() => {
    const len = jalaliMonthLength(view.jy, view.jm);
    const lead = jalaliMonthStartColumn(view.jy, view.jm);
    const cells = Array.from({ length: lead }, () => null);
    for (let d = 1; d <= len; d += 1) cells.push(d);
    return cells;
  }, [view.jy, view.jm]);

  const stepMonth = (delta) => {
    setView((v) => {
      let jm = v.jm + delta;
      let jy = v.jy;
      if (jm > 12) { jm = 1; jy += 1; }
      if (jm < 1) { jm = 12; jy -= 1; }
      return { jy, jm };
    });
  };

  const commit = (parts) => {
    onChange(toInputValue(parts, withTime));
  };

  const pickDay = (jd) => {
    commit({
      jy: view.jy,
      jm: view.jm,
      jd,
      hours: parsed?.hours ?? 9,
      minutes: parsed?.minutes ?? 0,
    });
    // With a time field the panel stays open so the clock can be set in the
    // same interaction; a date-only picker has nothing left to do.
    if (!withTime) setOpen(false);
  };

  const setClock = (hours, minutes) => {
    const base = parsed ?? { ...today, jd: today.jd };
    commit({ jy: base.jy, jm: base.jm, jd: base.jd, hours, minutes });
  };

  const jumpToday = () => {
    const now = new Date();
    onChange(dateToInputValue(now, withTime));
    setView({ jy: today.jy, jm: today.jm });
    if (!withTime) setOpen(false);
  };

  const clear = (e) => {
    e.stopPropagation();
    onChange("");
  };

  const display = value ? formatInputValue(value, withTime) : "";

  return (
    <div className={`jdp ${className}`} ref={rootRef}>
      <button
        type="button"
        id={id}
        className={`jdp__trigger ${open ? "jdp__trigger--open" : ""} ${!display ? "jdp__trigger--empty" : ""}`}
        onClick={() => !disabled && setOpen((o) => !o)}
        disabled={disabled}
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <CalendarDays size={16} className="jdp__trigger-icon" />
        <span className="jdp__trigger-value">{display || placeholder}</span>
        {/* Names the calendar system explicitly, so there is never any doubt
            about which calendar the number belongs to. */}
        <span className="jdp__badge">شمسی</span>
        {clearable && display && !disabled && (
          <span
            className="jdp__clear"
            role="button"
            tabIndex={-1}
            aria-label="پاک کردن تاریخ"
            onClick={clear}
          >
            <X size={13} />
          </span>
        )}
      </button>

      {/* A hidden mirror of the value keeps native form validation working,
          since the visible control is a button rather than an input. */}
      {required && (
        <input
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
          required
          value={value || ""}
          onChange={() => {}}
        />
      )}

      {open && (
        <div className="jdp__panel" ref={panelRef} role="dialog" aria-label="تقویم شمسی">
          <div className="jdp__header">
            <button type="button" className="jdp__nav" onClick={() => stepMonth(-1)} aria-label="ماه قبل">
              <ChevronRight size={16} />
            </button>
            <div className="jdp__title">
              <span className="jdp__title-month">{JALALI_MONTHS[view.jm - 1]}</span>
              <span className="jdp__title-year">{toFaDigits(view.jy)}</span>
            </div>
            <button type="button" className="jdp__nav" onClick={() => stepMonth(1)} aria-label="ماه بعد">
              <ChevronLeft size={16} />
            </button>
          </div>

          <div className="jdp__weekdays">
            {JALALI_WEEKDAYS.map((w, i) => (
              <span key={i} className={`jdp__weekday ${i === 6 ? "jdp__weekday--holiday" : ""}`}>{w}</span>
            ))}
          </div>

          <div className="jdp__grid">
            {grid.map((jd, i) =>
              jd === null ? (
                <span key={`e${i}`} className="jdp__cell jdp__cell--empty" />
              ) : (
                <button
                  key={jd}
                  type="button"
                  className={[
                    "jdp__cell",
                    isJalaliToday(view.jy, view.jm, jd) ? "jdp__cell--today" : "",
                    parsed && parsed.jy === view.jy && parsed.jm === view.jm && parsed.jd === jd
                      ? "jdp__cell--selected"
                      : "",
                    i % 7 === 6 ? "jdp__cell--holiday" : "",
                  ].join(" ")}
                  onClick={() => pickDay(jd)}
                >
                  {toFaDigits(jd)}
                </button>
              )
            )}
          </div>

          {withTime && (
            <div className="jdp__time">
              <Clock size={14} className="jdp__time-icon" />
              <span className="jdp__time-label">ساعت</span>
              <div className="jdp__time-fields">
                <select
                  className="jdp__time-select"
                  value={parsed?.hours ?? 9}
                  onChange={(e) => setClock(Number(e.target.value), parsed?.minutes ?? 0)}
                  aria-label="ساعت"
                >
                  {Array.from({ length: 24 }, (_, h) => (
                    <option key={h} value={h}>{toFaDigits(String(h).padStart(2, "0"))}</option>
                  ))}
                </select>
                <span className="jdp__time-sep">:</span>
                <select
                  className="jdp__time-select"
                  value={parsed?.minutes ?? 0}
                  onChange={(e) => setClock(parsed?.hours ?? 9, Number(e.target.value))}
                  aria-label="دقیقه"
                >
                  {[0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55].map((m) => (
                    <option key={m} value={m}>{toFaDigits(String(m).padStart(2, "0"))}</option>
                  ))}
                </select>
              </div>
            </div>
          )}

          <div className="jdp__footer">
            <button type="button" className="jdp__footer-btn" onClick={jumpToday}>
              {withTime ? "اکنون" : "امروز"}
            </button>
            <button type="button" className="jdp__footer-btn jdp__footer-btn--primary" onClick={() => setOpen(false)}>
              تأیید
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
