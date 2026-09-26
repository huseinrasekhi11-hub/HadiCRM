import { useMemo, useState } from "react";
import { UserCog, Loader2 } from "lucide-react";
import { useModalBehavior } from "../hooks/useModalBehavior";
import { usePermissions } from "../hooks/usePermissions";
import { isAdminOnly } from "../permissions";

export default function AssignModal({ users, currentOwnerId, onClose, onSubmit }) {
  const dialogRef = useModalBehavior(onClose);
  const { isAdmin } = usePermissions();

  /*
   * Referral is a sideways move between people who work the pipeline.
   * A salesperson pushing a case onto an admin or CEO is an escalation
   * wearing a referral's clothes: it leaves the case owned by someone who
   * does not run a queue, and it lands in the admin's personal statistics.
   * Supervisory accounts are therefore not offered as targets — an admin
   * can still pull any case to themselves, since they keep the full list.
   */
  const selectableUsers = useMemo(
    () => (isAdmin ? users : users.filter((u) => !isAdminOnly(u.role))),
    [users, isAdmin]
  );
  const [ownerId, setOwnerId] = useState("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    if (!ownerId) { setError("یک کارشناس انتخاب کنید."); return; }
    if (!selectableUsers.some((u) => String(u.id) === String(ownerId))) {
      setError("ارجاع به این کاربر مجاز نیست.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await onSubmit(Number(ownerId), note.trim() || null);
    } catch {
      setError("ارجاع با خطا مواجه شد.");
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" ref={dialogRef} role="dialog" aria-modal="true"
        onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <div className="modal__icon-bg"><UserCog size={20} /></div>
          <div>
            <h2 className="modal__title">ارجاع پرونده</h2>
            <p className="modal__subtitle">مسئول پیگیری این پرونده را مشخص کنید.</p>
          </div>
        </div>
        <form onSubmit={handleSubmit}>
          <label className="field">
            <span className="field__label">کارشناس <span className="text-red-500">*</span></span>
            <select className="crm-select" value={ownerId} onChange={(e) => setOwnerId(e.target.value)}>
              <option value="" disabled>انتخاب کارشناس…</option>
              {selectableUsers.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name}{u.id === currentOwnerId ? " (مسئول فعلی)" : ""}
                </option>
              ))}
            </select>
          </label>
          {!isAdmin && (
            <p className="field__hint">
              برای ارجاع به مدیریت، از گزینه «ارجاع به مدیر» در منوی پرونده استفاده کنید.
            </p>
          )}
          <label className="field">
            <span className="field__label">یادداشت (اختیاری)</span>
            <input className="premium-input" value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          {error && <div className="form-error-banner">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>انصراف</button>
            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting ? <Loader2 size={16} className="spin" /> : "ارجاع"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
