import { useEffect, useState } from "react";
import { FileWarning, Loader2, RotateCcw } from "lucide-react";
import { getDeletedLeadDetail } from "../api/client";
import { useModalBehavior } from "../hooks/useModalBehavior";
import { statusLabel } from "../leadStatus";
import { formatDateTime, formatRial } from "../utils/persian";
import "./DeletedLeadDetailModal.css";

/**
 * Snapshot view of a deleted lead.
 *
 * Opening /leads/:id for a deleted record used to 404 — the lead is
 * soft-deleted and the lead endpoint refuses to serve it, so the audit page's
 * "view file" link always produced an error screen. A deleted lead has no
 * live record to show; what exists is the deletion audit snapshot, which is
 * what this reads instead.
 */

const LOSS_REASON_LABELS = {
  price: "قیمت",
  competitor: "رقیب",
  no_budget: "عدم بودجه",
  no_need: "عدم نیاز",
  timing: "زمان‌بندی",
  unreachable: "عدم دسترسی",
  other: "سایر",
};

/* Snapshot keys worth surfacing, in reading order. Anything absent is
   skipped rather than rendered as an empty row. */
const SNAPSHOT_FIELDS = [
  ["customer_name", "نام مشتری"],
  ["mobile", "موبایل"],
  ["source", "منبع"],
  ["need", "نیاز"],
  ["city", "شهر"],
  ["company", "شرکت"],
  ["notes", "یادداشت"],
  ["sold_products", "کالاهای فروخته‌شده"],
];

function Row({ label, value, ltr = false }) {
  if (value == null || value === "") return null;
  return (
    <div className="dld-row">
      <span className="dld-row__label">{label}</span>
      <span className={`dld-row__value ${ltr ? "dld-row__value--ltr" : ""}`}>{value}</span>
    </div>
  );
}

export default function DeletedLeadDetailModal({ auditId, summary, onClose, onRestore }) {
  const dialogRef = useModalBehavior(onClose);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    getDeletedLeadDetail(auditId)
      .then((d) => { if (!cancelled) setDetail(d); })
      .catch(() => { if (!cancelled) setError("دریافت جزئیات این حذف ممکن نشد."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [auditId]);

  // The list row is already on screen, so its fields render immediately and
  // the snapshot fills in behind them rather than showing a blank dialog.
  const data = detail || summary || {};
  const snapshot = detail?.snapshot || {};
  const restored = Boolean(data.restored_at);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal--premium dld-modal" ref={dialogRef} role="dialog" aria-modal="true"
        onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <div className="modal__icon-bg dld-icon"><FileWarning size={20} /></div>
          <div>
            <h2 className="modal__title">{data.customer_name || "پرونده حذف‌شده"}</h2>
            <p className="modal__subtitle">
              این پرونده حذف شده است و نسخه‌ی زنده‌ای از آن وجود ندارد. آنچه می‌بینید
              اسنپ‌شات ثبت‌شده در لحظه‌ی حذف است.
            </p>
          </div>
        </div>

        {error && <div className="alert-banner alert-banner--error">{error}</div>}

        {/* --- Deletion audit --- */}
        <section className="dld-section">
          <h3 className="dld-section__title">ممیزی حذف</h3>
          <Row label="حذف‌شده توسط" value={data.deleted_by_full_name || (data.deleted_by_id ? `#${data.deleted_by_id}` : null)} />
          <Row label="زمان حذف" value={data.deleted_at ? formatDateTime(data.deleted_at) : null} />
          <Row label="مالک اصلی" value={data.owner_full_name || "—"} />
          <Row label="وضعیت پیش از حذف" value={data.previous_status ? statusLabel(data.previous_status) : null} />
          {restored && (
            <Row label="احیا شده در" value={formatDateTime(data.restored_at)} />
          )}
        </section>

        {/* --- Commercial --- */}
        {(data.sale_amount || data.invoice_number || data.loss_reason) && (
          <section className="dld-section">
            <h3 className="dld-section__title">اطلاعات مالی</h3>
            <Row label="مبلغ" value={data.sale_amount ? formatRial(data.sale_amount) : null} />
            <Row label="شماره فاکتور" value={data.invoice_number} ltr />
            <Row label="دلیل عدم فروش" value={LOSS_REASON_LABELS[data.loss_reason] || data.loss_reason} />
          </section>
        )}

        {/* --- Snapshot --- */}
        <section className="dld-section">
          <h3 className="dld-section__title">اطلاعات پرونده در لحظه‌ی حذف</h3>
          {loading ? (
            <div className="dld-loading"><Loader2 size={16} className="spin" /> در حال دریافت اسنپ‌شات…</div>
          ) : (
            <>
              <Row label="نام مشتری" value={snapshot.customer_name ?? data.customer_name} />
              <Row label="موبایل" value={snapshot.mobile ?? data.mobile} ltr />
              {SNAPSHOT_FIELDS.filter(([k]) => !["customer_name", "mobile"].includes(k)).map(([key, label]) => (
                <Row key={key} label={label} value={snapshot[key]} />
              ))}
              {!loading && Object.keys(snapshot).length === 0 && (
                <p className="dld-empty">اسنپ‌شاتی برای این حذف ذخیره نشده است.</p>
              )}
            </>
          )}
        </section>

        <div className="modal-actions">
          <button type="button" className="btn-ghost" onClick={onClose}>بستن</button>
          {!restored && onRestore && (
            <button type="button" className="btn-primary" onClick={() => onRestore(data)}>
              <RotateCcw size={15} /> احیای پرونده
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
