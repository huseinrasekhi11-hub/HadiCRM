import { useState } from "react";
import { UserPlus, Loader2 } from "lucide-react";
import { createLead } from "../api/client";
import { useToast } from "./Toast";
import "./NewLeadModal.css";
import { useModalBehavior } from "../hooks/useModalBehavior";
import { getErrorMessage } from "../utils/apiError";

// Shared by the Leads page (desktop) and the mobile quick-action FAB.
// Backend Feature 1: if the mobile already exists AND belongs to the
// current user (or a role that can see all leads), the API returns the
// EXISTING lead with duplicate_count >= 1 — we surface that explicitly
// instead of pretending a new file was created.
// SECURITY: if the mobile belongs to a DIFFERENT user's lead that this
// user cannot view, the API deliberately does NOT return that lead's
// data (no id, no customer_name, nothing identifying) — it returns
// { status: "duplicate_attached", is_duplicate: true, message } instead.
// In that case we must not call onCreated() with a navigable id, since
// there is no lead this user is allowed to open.
export default function NewLeadModal({ onClose, onCreated }) {
  const dialogRef = useModalBehavior(onClose);
  const notify = useToast();
  const [formData, setFormData] = useState({ customer_name: "", mobile: "", source: "", need: "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const set = (key) => (e) => setFormData((p) => ({ ...p, [key]: e.target.value }));

  async function handleSubmit(e) {
    e.preventDefault();
    if (!formData.customer_name.trim() || !formData.mobile.trim()) {
      setError("نام مشتری و شماره موبایل الزامی است.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const lead = await createLead({
        customer_name: formData.customer_name.trim(),
        mobile: formData.mobile.trim(),
        source: formData.source.trim(),
        need: formData.need.trim() || null,
      });

      if (lead.is_duplicate && !lead.id) {
        // Attached to an existing lead this user cannot view. There is
        // nothing to navigate to — show the message and just close.
        notify(
          lead.message || "این شماره قبلاً در سیستم ثبت شده است.",
          "info"
        );
        onClose();
        return;
      }

      if ((lead.duplicate_count || 0) > 0) {
        notify(
          `این شماره قبلاً ثبت شده بود؛ ثبت جدید به پرونده‌ی موجود متصل شد (ثبت شمارهٔ ${lead.duplicate_count + 1}).`,
          "info"
        );
      } else {
        notify("لید جدید ایجاد شد.", "success");
      }
      onCreated(lead);
    } catch (err) {
      setError(getErrorMessage(err, "ثبت لید با خطا مواجه شد. اطلاعات را بررسی کنید."));
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" ref={dialogRef} role="dialog" aria-modal="true"
        onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <div className="modal__icon-bg"><UserPlus size={20} /></div>
          <div>
            <h2 className="modal__title">لید جدید</h2>
            <p className="modal__subtitle">
              اگر موبایل تکراری باشد، به‌صورت خودکار به پروندهٔ موجود متصل می‌شود.
            </p>
          </div>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="form-grid">
            <label className="field">
              <span className="field__label">نام مشتری <span className="text-red-500">*</span></span>
              <input className="premium-input" value={formData.customer_name} onChange={set("customer_name")} autoFocus required />
            </label>
            <label className="field">
              <span className="field__label">موبایل <span className="text-red-500">*</span></span>
              <input
                className="premium-input premium-input--ltr"
                inputMode="tel"
                placeholder="09…"
                value={formData.mobile}
                onChange={set("mobile")}
                required
              />
            </label>
          </div>
          <label className="field">
            <span className="field__label">منبع ورودی</span>
            <input className="premium-input" placeholder="مثلاً: اینستاگرام، تماس تلفنی" value={formData.source} onChange={set("source")} />
          </label>
          <label className="field">
            <span className="field__label">شرح نیاز</span>
            <textarea className="premium-input" rows={2} placeholder="مشتری دقیقاً چه چیزی نیاز دارد؟" value={formData.need} onChange={set("need")} />
          </label>
          {error && <div className="form-error-banner">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>انصراف</button>
            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting ? <Loader2 size={16} className="spin" /> : "ثبت لید"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
