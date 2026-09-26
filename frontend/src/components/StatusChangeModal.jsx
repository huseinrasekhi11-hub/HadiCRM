import { useState } from "react";
import { Loader2, Target, AlertTriangle, CheckCircle2 } from "lucide-react";
import { statusLabel, LOSS_REASONS, WON_STATUS, LOST_STATUS } from "../leadStatus";
import "./StatusChangeModal.css";
import { useModalBehavior } from "../hooks/useModalBehavior";
import { getErrorMessage } from "../utils/apiError";

export default function StatusChangeModal({ targetStatus, onClose, onSubmit }) {
  const dialogRef = useModalBehavior(onClose);
  const isLost = targetStatus === LOST_STATUS;
  const isWon = targetStatus === WON_STATUS;
  const [lossReason, setLossReason] = useState("");
  const [saleAmount, setSaleAmount] = useState("");
  const [soldProducts, setSoldProducts] = useState("");
  const [invoiceNumber, setInvoiceNumber] = useState("");
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    if (isLost && !lossReason) {
      setError("انتخاب دلیل عدم فروش الزامی است.");
      return;
    }
    setSubmitting(true);
    try {
      const extra = {};
      if (isLost) {
        extra.loss_reason = lossReason;
        if (resolutionNotes.trim()) extra.resolution_notes = resolutionNotes.trim();
      }
      if (isWon) {
        if (saleAmount) extra.sale_amount = Number(saleAmount);
        if (soldProducts.trim()) extra.sold_products = soldProducts.trim();
        if (invoiceNumber.trim()) extra.invoice_number = invoiceNumber.trim();
        if (resolutionNotes.trim()) extra.resolution_notes = resolutionNotes.trim();
      }
      await onSubmit(extra);
    } catch (err) {
      setError(getErrorMessage(err, "تغییر وضعیت با خطا مواجه شد."));
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal--premium status-change-modal" ref={dialogRef} role="dialog" aria-modal="true"
        onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <div className={`modal__icon-bg ${isWon ? "bg-emerald-100" : isLost ? "bg-rose-100" : "bg-blue-100"}`}>
            {isWon ? <Target size={20} className="text-emerald-600" /> :
             isLost ? <AlertTriangle size={20} className="text-rose-600" /> :
             <CheckCircle2 size={20} className="text-blue-600" />}
          </div>
          <div>
            <h2 className="modal__title m-0">
              {isWon ? "ثبت فاکتور" : isLost ? "بستن پرونده (ناموفق)" : `انتقال به ${statusLabel(targetStatus)}`}
            </h2>
            <p className="modal__subtitle">
              {isWon ? "تبریک! جزئیات فروش را وارد کنید." :
               isLost ? "لطفاً دلیل عدم موفقیت را مشخص کنید." :
               "آیا از تغییر وضعیت اطمینان دارید؟"}
            </p>
          </div>
        </div>
        <form onSubmit={handleSubmit} className="modal-form mt-4">
          {isLost && (
            <div className="loss-reason-section">
              <label className="field__label mb-2 block">دلیل عدم فروش <span className="text-red-500">*</span></label>
              <div className="loss-reason-grid">
                {LOSS_REASONS.map((r) => (
                  <button
                    type="button"
                    key={r.value}
                    className={`loss-chip ${lossReason === r.value ? "loss-chip--active" : ""}`}
                    onClick={() => setLossReason(r.value)}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
            </div>
          )}
          {isWon && (
            <div className="won-form-grid">
              <label className="field">
                <span className="field__label">مبلغ فروش (تومان)</span>
                <input type="number" className="premium-input premium-input--ltr"
                  value={saleAmount} onChange={(e) => setSaleAmount(e.target.value)} placeholder="مثلاً: 50000000" />
              </label>
              <label className="field">
                <span className="field__label">شماره فاکتور</span>
                <input className="premium-input premium-input--ltr"
                  value={invoiceNumber} onChange={(e) => setInvoiceNumber(e.target.value)} placeholder="اختیاری" />
              </label>
              <label className="field col-span-2">
                <span className="field__label">کالاهای فروخته‌شده</span>
                <input className="premium-input"
                  value={soldProducts} onChange={(e) => setSoldProducts(e.target.value)}
                  placeholder="مثلاً: ۲ عدد داکت اسپلیت ۳۶۰۰۰" />
              </label>
            </div>
          )}
          {(isWon || isLost) && (
            <label className="field mt-2">
              <span className="field__label">یادداشت پایانی (اختیاری)</span>
              <textarea className="premium-input" rows={2}
                value={resolutionNotes} onChange={(e) => setResolutionNotes(e.target.value)} placeholder="توضیحات تکمیلی..." />
            </label>
          )}
          {error && <div className="form-error-banner">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>انصراف</button>
            <button
              type="submit"
              className={`btn-primary ${isWon ? "bg-emerald-500 border-emerald-600 hover:bg-emerald-600" : isLost ? "bg-rose-500 border-rose-600 hover:bg-rose-600" : ""}`}
              disabled={submitting}
            >
              {submitting ? <Loader2 size={16} className="spin" /> : "تایید و ثبت"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
