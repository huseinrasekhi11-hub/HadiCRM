import { useState } from "react";
import { Loader2, KeyRound } from "lucide-react";
import { changePassword } from "../api/client";
import { useModalBehavior } from "../hooks/useModalBehavior";
import "./ChangePasswordModal.css";

/**
 * Self-service password change.
 *
 * Before this existed there was no way for anyone — user or admin — to
 * change a password through the product. The endpoint requires the current
 * password, so a stolen session alone cannot take over the account, and
 * every other session is revoked server-side once the change succeeds.
 */
export default function ChangePasswordModal({ onClose, onChanged }) {
  const dialogRef = useModalBehavior(onClose);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");

    if (newPassword.length < 8) {
      setError("رمز جدید باید حداقل ۸ کاراکتر باشد.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("تکرار رمز جدید با آن یکسان نیست.");
      return;
    }
    if (newPassword === currentPassword) {
      setError("رمز جدید باید با رمز فعلی متفاوت باشد.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await changePassword(currentPassword, newPassword);
      setDone(true);
      if (onChanged) onChanged(res);
    } catch (err) {
      const status = err?.response?.status;
      if (status === 429) {
        setError("تلاش‌های ناموفق بیش از حد مجاز؛ کمی بعد دوباره تلاش کنید.");
      } else if (status === 400) {
        setError(err?.response?.data?.detail || "رمز عبور فعلی اشتباه است.");
      } else {
        setError("تغییر رمز انجام نشد. دوباره تلاش کنید.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="change-password-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__header">
          <div className="modal__icon-bg">
            <KeyRound size={20} />
          </div>
          <div>
            <h2 className="modal__title" id="change-password-title">
              تغییر رمز عبور
            </h2>
            <p className="modal__subtitle">
              پس از تغییر رمز، همهٔ نشست‌های دیگر این حساب خارج می‌شوند.
            </p>
          </div>
        </div>

        {done ? (
          <>
            <div className="change-password__done" role="status">
              رمز عبور با موفقیت تغییر کرد.
            </div>
            <div className="modal-actions">
              <button type="button" className="btn-primary" onClick={onClose}>
                بستن
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={handleSubmit} className="change-password__form">
            <div className="form-group">
              <label className="form-label" htmlFor="current-password">
                رمز عبور فعلی
              </label>
              <input
                id="current-password"
                type="password"
                autoComplete="current-password"
                className="premium-input"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="new-password">
                رمز عبور جدید
              </label>
              <input
                id="new-password"
                type="password"
                autoComplete="new-password"
                className="premium-input"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={8}
              />
              <span className="change-password__hint">حداقل ۸ کاراکتر</span>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="confirm-password">
                تکرار رمز عبور جدید
              </label>
              <input
                id="confirm-password"
                type="password"
                autoComplete="new-password"
                className="premium-input"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                minLength={8}
              />
            </div>

            {error && (
              <div className="form-error-banner" role="alert">
                {error}
              </div>
            )}

            <div className="modal-actions">
              <button type="button" className="btn-ghost" onClick={onClose}>
                انصراف
              </button>
              <button type="submit" className="btn-primary" disabled={submitting}>
                {submitting ? (
                  <>
                    <Loader2 size={16} className="spin" />
                    در حال ثبت…
                  </>
                ) : (
                  "تغییر رمز"
                )}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
