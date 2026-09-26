import { useState } from "react";
import { Loader2, PackagePlus } from "lucide-react";
import "./AddSaleItemModal.css";
import { useModalBehavior } from "../hooks/useModalBehavior";

// Structured per-product Rial capture (backend Feature 5). Replaces the
// legacy free-text sold_products for reliable per-product reporting.
export default function AddSaleItemModal({ products, onClose, onSubmit }) {
  const dialogRef = useModalBehavior(onClose);
  const [productId, setProductId] = useState("");
  const [amount, setAmount] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    const amountNum = Number(amount);
    if (!productId) { setError("یک کالا انتخاب کنید."); return; }
    if (!amount || Number.isNaN(amountNum) || amountNum < 0) {
      setError("مبلغ معتبر وارد کنید."); return;
    }
    setSubmitting(true);
    try {
      await onSubmit({ product_id: Number(productId), amount: amountNum });
    } catch (err) {
      setError(err?.response?.data?.detail || "ثبت قلم فروش با خطا مواجه شد.");
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" ref={dialogRef} role="dialog" aria-modal="true"
        onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <div className="modal__icon-bg"><PackagePlus size={20} /></div>
          <div>
            <h2 className="modal__title">افزودن قلم فروش</h2>
            <p className="modal__subtitle">کالا و مبلغ آن به ریال ثبت می‌شود.</p>
          </div>
        </div>
        <form onSubmit={handleSubmit}>
          <label className="field">
            <span className="field__label">کالا <span className="text-red-500">*</span></span>
            <select className="crm-select" value={productId} onChange={(e) => setProductId(e.target.value)}>
              <option value="" disabled>انتخاب کالا…</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field__label">مبلغ (ریال) <span className="text-red-500">*</span></span>
            <input
              type="number"
              className="premium-input premium-input--ltr"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="مثلاً: 50000000"
              min="0"
            />
          </label>
          {error && <div className="form-error-banner">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>انصراف</button>
            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting ? <Loader2 size={16} className="spin" /> : "ثبت قلم"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
