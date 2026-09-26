import { useState } from "react";
import { Loader2, CalendarClock } from "lucide-react";
import { FOLLOWUP_QUICK_OPTIONS, quickFollowUpToDate } from "../leadStatus";
import "./FollowUpModal.css";
import { useModalBehavior } from "../hooks/useModalBehavior";
import JalaliDatePicker from "./JalaliDatePicker";

function toLocalInputValue(date) {
  if (!date) return "";
  const d = new Date(date);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function FollowUpModal({ onClose, onSubmit }) {
  const dialogRef = useModalBehavior(onClose);
  const [option, setOption] = useState("tomorrow");
  const [customDate, setCustomDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    d.setHours(9, 0, 0, 0);
    return toLocalInputValue(d);
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    let next = null;
    if (option === "custom") next = new Date(customDate);
    else if (option !== "none") next = quickFollowUpToDate(option);
    if (option === "custom" && (!next || Number.isNaN(next.getTime()))) {
      setError("تاریخ انتخابی معتبر نیست.");
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit(next ? next.toISOString() : null);
    } catch {
      setError("تنظیم پیگیری با خطا مواجه شد.");
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" ref={dialogRef} role="dialog" aria-modal="true"
        onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <div className="modal__icon-bg"><CalendarClock size={20} /></div>
          <div>
            <h2 className="modal__title">زمان پیگیری بعدی</h2>
            <p className="modal__subtitle">برای این پرونده یادآوری پیگیری تنظیم کنید.</p>
          </div>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="followup-options">
            {FOLLOWUP_QUICK_OPTIONS.map((opt) => (
              <button
                type="button"
                key={opt.value}
                className={`followup-btn ${option === opt.value ? "followup-btn--active" : ""} ${opt.value === "none" ? "followup-btn--danger" : ""}`}
                onClick={() => setOption(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {option === "custom" && (
            <div className="mt-3">
              <JalaliDatePicker
                withTime
                value={customDate}
                onChange={setCustomDate}
              />
            </div>
          )}
          {error && <div className="form-error-banner mt-3">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>انصراف</button>
            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting ? <Loader2 size={16} className="spin" /> : "ثبت پیگیری"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
