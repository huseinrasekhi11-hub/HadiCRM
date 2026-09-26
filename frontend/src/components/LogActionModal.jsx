import { useState, useEffect } from "react";
import { Loader2, Activity, Clock } from "lucide-react";
import { ACTION_TYPES, FOLLOWUP_QUICK_OPTIONS, quickFollowUpToDate } from "../leadStatus";
import "./LogActionModal.css";
import { useModalBehavior } from "../hooks/useModalBehavior";
import JalaliDatePicker from "./JalaliDatePicker";

function toLocalInputValue(date) {
  if (!date) return "";
  const d = new Date(date);
  if (isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function LogActionModal({ initialData, onClose, onSubmit }) {
  const dialogRef = useModalBehavior(onClose);
  const isEditing = !!initialData;

  const [activityType, setActivityType] = useState(initialData?.activity_type || "call");
  const [title, setTitle] = useState(initialData?.title || "");
  const [description, setDescription] = useState(initialData?.description || "");
  const [outcome, setOutcome] = useState(initialData?.outcome || "");
  const [followUpOption, setFollowUpOption] = useState(null);
  const [customDate, setCustomDate] = useState("");
  const [noFollowUpReason, setNoFollowUpReason] = useState(initialData?.no_followup_reason || "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const selectedAction = ACTION_TYPES.find((a) => a.value === activityType);

  // Pre-fill follow-up data if editing
  useEffect(() => {
    if (initialData?.next_follow_up) {
      setFollowUpOption("custom");
      setCustomDate(toLocalInputValue(initialData.next_follow_up));
    } else if (initialData?.no_followup_reason) {
      setFollowUpOption("none");
    }
  }, [initialData]);

  function handlePickFollowUp(option) {
    setFollowUpOption(option);
    if (option === "custom" && !customDate) {
      const d = new Date();
      d.setDate(d.getDate() + 1);
      d.setHours(9, 0, 0, 0);
      setCustomDate(toLocalInputValue(d));
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");

    let nextFollowUp = null;
    if (followUpOption && followUpOption !== "none") {
      nextFollowUp = followUpOption === "custom"
        ? new Date(customDate)
        : quickFollowUpToDate(followUpOption);
    }

    if (!nextFollowUp && !noFollowUpReason.trim()) {
      setError("باید زمان پیگیری بعدی را مشخص کنید یا در صورت «بدون پیگیری»، دلیل آن را بنویسید.");
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit({
        activity_type: activityType,
        title: title.trim() || selectedAction?.label || "اقدام",
        description: description.trim() || null,
        outcome: outcome.trim() || null,
        next_follow_up: nextFollowUp ? nextFollowUp.toISOString() : null,
        no_followup_reason: nextFollowUp ? null : noFollowUpReason.trim(),
      });
    } catch (err) {
      setError(err?.response?.data?.detail || "ثبت اقدام با خطا مواجه شد.");
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal--premium log-action-modal" ref={dialogRef} role="dialog" aria-modal="true"
        onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <div className="modal__icon-bg"><Activity size={20} className="text-blue-600" /></div>
          <div>
            <h2 className="modal__title m-0">{isEditing ? "ویرایش اقدام" : "ثبت اقدام جدید"}</h2>
            <p className="modal__subtitle">جزئیات ارتباط با مشتری را ثبت کنید.</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="modal-form mt-4">
          
          {/* Action Type Selector */}
          <div className="action-type-selector">
            {ACTION_TYPES.map((a) => (
              <button
                type="button"
                key={a.value}
                className={`action-chip ${activityType === a.value ? "action-chip--active" : ""}`}
                onClick={() => setActivityType(a.value)}
              >
                <span className="action-chip__emoji">{a.emoji}</span>
                {a.label}
              </button>
            ))}
          </div>

          <div className="form-grid">
            <label className="field">
              <span className="field__label">عنوان (اختیاری)</span>
              <input
                className="premium-input"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={selectedAction?.label}
              />
            </label>
            <label className="field">
              <span className="field__label">نتیجه (اختیاری)</span>
              <input
                className="premium-input"
                value={outcome}
                onChange={(e) => setOutcome(e.target.value)}
                placeholder="مثلاً: پاسخ نداد / علاقه‌مند"
              />
            </label>
          </div>

          <label className="field">
            <span className="field__label">توضیحات</span>
            <textarea
              className="premium-input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="چه اتفاقی افتاد؟"
            />
          </label>

          {/* Follow-up Section */}
          <div className="followup-panel">
            <div className="followup-panel__header">
              <Clock size={16} className="text-blue-500" />
              <span className="font-bold text-slate-800 text-sm">پیگیری بعدی چه زمانی است؟ <span className="text-red-500">*</span></span>
            </div>
            
            <div className="followup-options">
              {FOLLOWUP_QUICK_OPTIONS.map((opt) => (
                <button
                  type="button"
                  key={opt.value}
                  className={`followup-btn ${followUpOption === opt.value ? "followup-btn--active" : ""} ${opt.value === "none" ? "followup-btn--danger" : ""}`}
                  onClick={() => handlePickFollowUp(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            {followUpOption === "custom" && (
              <div className="mt-3 animate-slide-down">
                <JalaliDatePicker
                  withTime
                  value={customDate}
                  onChange={setCustomDate}
                />
              </div>
            )}

            {followUpOption === "none" && (
              <div className="mt-3 animate-slide-down">
                <textarea
                  className="premium-input"
                  placeholder="دلیل عدم پیگیری را بنویسید…"
                  value={noFollowUpReason}
                  onChange={(e) => setNoFollowUpReason(e.target.value)}
                  rows={2}
                />
              </div>
            )}
          </div>

          {error && <div className="form-error-banner">{error}</div>}

          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>انصراف</button>
            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting ? <Loader2 size={16} className="spin" /> : (isEditing ? "ذخیره تغییرات" : "ثبت اقدام")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
