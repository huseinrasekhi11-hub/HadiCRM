import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Copy, Link2, Clock, FileSignature, ShieldCheck, ChevronLeft, Sparkles, Loader2,
} from "lucide-react";
import { getLeadDuplicateHistory } from "../api/client";
import { statusLabel, statusColor } from "../leadStatus";
import HealthBadge from "./HealthBadge";
import "./DuplicateCenter.css";
import { formatDate, formatDateTime } from "../utils/persian";

const fmtDate = formatDate;
const fmtDateTime = formatDateTime;

const MATCH_LABELS = {
  mobile: "تطبیق با شماره موبایل",
  mobile_and_name: "تطبیق با موبایل و نام",
};

const trim = (v) => (v || "").trim();

/* One comparable field; highlights values that differ from the canonical record. */
function FieldRow({ label, value, canonicalValue, ltr = false }) {
  const differs = canonicalValue !== undefined && trim(value) !== trim(canonicalValue);
  return (
    <div className={`dup-field ${differs ? "dup-field--diff" : ""}`}>
      <span className="dup-field__label">
        {label}
        {differs && <span className="dup-field__diff-tag">متفاوت از اصلی</span>}
      </span>
      <span className={`dup-field__value ${ltr ? "dup-field__value--ltr" : ""}`}>
        {value || "—"}
      </span>
    </div>
  );
}

export default function DuplicateCenter({ lead, related = [] }) {
  const navigate = useNavigate();
  const [submissions, setSubmissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError("");
    getLeadDuplicateHistory(lead.id)
      .then((d) => mounted && setSubmissions(d))
      .catch(() => mounted && setError("دریافت تاریخچه‌ی ثبت‌های تکراری ناموفق بود."))
      .finally(() => mounted && setLoading(false));
    return () => { mounted = false; };
  }, [lead.id]);

  // ثبت اصلی + ثبت‌های تکراری
  const totalSubmissions = (lead.duplicate_count || 0) + 1;

  return (
    <div className="dup-center card ws-panel">
      {/* --- Summary strip --- */}
      <div className="dup-summary">
        <div className="dup-summary__item">
          <span className="dup-summary__label">مجموع ثبت‌ها</span>
          <span className="dup-summary__value">{totalSubmissions}</span>
        </div>
        <div className="dup-summary__item">
          <span className="dup-summary__label">اولین ثبت</span>
          <span className="dup-summary__value dup-summary__value--sm">{fmtDate(lead.created_at)}</span>
        </div>
        {submissions.length > 0 && (
          <div className="dup-summary__item">
            <span className="dup-summary__label">آخرین ثبت تکراری</span>
            <span className="dup-summary__value dup-summary__value--sm">
              {fmtDate(submissions[0].submitted_at)}
            </span>
          </div>
        )}
      </div>

      {/* --- Original registration (canonical record) --- */}
      <section className="dup-section">
        <h3 className="dup-section__title">
          <FileSignature size={15} /> ثبت اصلی
        </h3>
        <div className="dup-card dup-card--original">
          <div className="dup-card__grid">
            <FieldRow label="نام مشتری" value={lead.customer_name} />
            <FieldRow label="موبایل" value={lead.mobile} ltr />
            <FieldRow label="منبع" value={lead.source} />
            <FieldRow label="نیاز" value={lead.need} />
          </div>
          <div className="dup-card__foot">
            <Clock size={12} /> {fmtDateTime(lead.created_at)}
          </div>
        </div>
      </section>

      {/* --- Repeated submissions attached to this file --- */}
      <section className="dup-section">
        <h3 className="dup-section__title">
          <Copy size={15} /> ثبت‌های تکراری
          {submissions.length > 0 && <span className="dup-section__count">{submissions.length}</span>}
        </h3>

        {error && <div className="alert-banner alert-banner--error">{error}</div>}

        {loading ? (
          <div className="dup-loading">
            <Loader2 size={18} className="spin" /> در حال دریافت تاریخچه…
          </div>
        ) : submissions.length === 0 ? (
          <div className="dup-empty">
            <Sparkles size={18} />
            ثبت تکراری برای این پرونده وجود ندارد.
          </div>
        ) : (
          submissions.map((sub) => (
            <div key={sub.id} className="dup-card">
              <div className="dup-card__head">
                <span className="dup-card__index">ثبت #{sub.submission_index + 1}</span>
                <span className="dup-match-badge">
                  <ShieldCheck size={12} /> {MATCH_LABELS[sub.matched_by] || sub.matched_by}
                </span>
              </div>
              <div className="dup-card__grid">
                <FieldRow label="نام مشتری" value={sub.customer_name} canonicalValue={lead.customer_name} />
                <FieldRow label="موبایل" value={sub.mobile} ltr />
                <FieldRow label="منبع" value={sub.source} canonicalValue={lead.source} />
                <FieldRow label="نیاز" value={sub.need} canonicalValue={lead.need} />
              </div>
              {sub.notes && <div className="dup-card__notes">یادداشت ثبت: {sub.notes}</div>}
              <div className="dup-card__foot">
                <span>{sub.submitted_by_full_name || "کاربر"}</span>
                <span className="dup-meta-dot">•</span>
                <Clock size={12} /> {fmtDateTime(sub.submitted_at)}
              </div>
            </div>
          ))
        )}
      </section>

      {/* --- Related leads: separate files sharing the normalized mobile --- */}
      <section className="dup-section">
        <h3 className="dup-section__title">
          <Link2 size={15} /> پرونده‌های هم‌شماره
        </h3>
        <p className="dup-section__hint">
          پرونده‌هایی که همان شماره موبایل (پس از نرمال‌سازی) را دارند اما جدا از این پرونده ساخته شده‌اند.
          نمایش بر اساس سطح دسترسی شماست.
        </p>

        {related.length === 0 ? (
          <div className="dup-empty dup-empty--ok">
            <Sparkles size={18} />
            پرونده‌ی جداگانه‌ای با این شماره وجود ندارد؛ تاریخچه‌ی مشتری یکپارچه است.
          </div>
        ) : (
          related.map((r) => (
            <button key={r.id} className="dup-related-row" onClick={() => navigate(`/leads/${r.id}`)}>
              <span className="dup-related-row__bar" style={{ background: statusColor(r.status) }} />
              <span className="dup-related-row__body">
                <span className="dup-related-row__name">{r.customer_name}</span>
                <span className="dup-related-row__meta">
                  <span style={{ color: statusColor(r.status) }}>{statusLabel(r.status)}</span>
                  <span className="dup-meta-dot">•</span>
                  <span>{fmtDate(r.created_at)}</span>
                  {(r.duplicate_count || 0) > 0 && (
                    <>
                      <span className="dup-meta-dot">•</span>
                      <span>{r.duplicate_count} ثبت تکراری</span>
                    </>
                  )}
                </span>
              </span>
              {r.health && <HealthBadge health={r.health} size="md" />}
              <ChevronLeft size={16} className="dup-related-row__chevron" />
            </button>
          ))
        )}
      </section>
    </div>
  );
}
