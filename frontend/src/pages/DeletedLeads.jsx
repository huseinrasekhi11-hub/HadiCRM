import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import DeletedLeadDetailModal from "../components/DeletedLeadDetailModal";
import {
  Trash2, Search, RotateCcw, X, ChevronDown, User as UserIcon,
  Calendar, Loader2, Inbox,
} from "lucide-react";
import {
  getDeletedLeads, restoreDeletedLead, getUsers,
} from "../api/client";
import { useAuth } from "../hooks/useAuth";
import { useToast } from "../hooks/useToast";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import InfiniteScroll from "../components/InfiniteScroll";
import AppShell from "../components/AppShell";
import AccessDenied from "../components/AccessDenied";
import { isAdminOnly } from "../permissions";
import { statusLabel } from "../leadStatus";
import { formatDateTime } from "../utils/persian";
import "./DeletedLeads.css";
import JalaliDatePicker from "../components/JalaliDatePicker";
import { getErrorMessage } from "../utils/apiError";

const PAGE_SIZE = 30;

function fmtRial(n) {
  if (n === null || n === undefined) return "—";
  return new Intl.NumberFormat("fa-IR").format(n) + " ریال";
}

export default function DeletedLeads() {
  const { user } = useAuth();
  const allowed = isAdminOnly(user?.role);
  const notify = useToast();

  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [restoringId, setRestoringId] = useState(null);
  const [viewing, setViewing] = useState(null);

  const [search, setSearch] = useState("");
  const [deletedById, setDeletedById] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [includeRestored, setIncludeRestored] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const [teamUsers, setTeamUsers] = useState([]);

  const debouncedSearch = useDebouncedValue(search.trim(), 300);

  useEffect(() => {
    if (!allowed) return;
    getUsers().then(setTeamUsers).catch(() => {});
  }, [allowed]);

  const buildParams = (skip) => ({
    search: debouncedSearch || undefined,
    deleted_by_id: deletedById || undefined,
    owner_id: ownerId || undefined,
    date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
    date_to: dateTo ? new Date(dateTo).toISOString() : undefined,
    include_restored: includeRestored,
    skip,
    limit: PAGE_SIZE,
  });

  const load = (append = false) => {
    if (!allowed) return;
    const skip = append ? rows.length : 0;
    if (append) setLoadingMore(true); else setLoading(true);
    setError("");
    getDeletedLeads(buildParams(skip))
      .then((data) => {
        setRows((prev) => (append ? [...prev, ...data] : data));
        // بک‌اند تعداد کل را برنمی‌گرداند؛ برای صفحه‌بندی از طول صفحه
        // استفاده می‌کنیم: اگر داده‌ی برگشتی کمتر از PAGE_SIZE بود، یعنی ادامه ندارد.
        setTotal((prevTotal) => (append ? prevTotal : Infinity));
        if (data.length < PAGE_SIZE) setTotal(skip + data.length);
      })
      .catch(() => setError("دریافت لیدهای حذف‌شده با خطا مواجه شد."))
      .finally(() => { setLoading(false); setLoadingMore(false); });
  };

  useEffect(() => {
    load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, deletedById, ownerId, dateFrom, dateTo, includeRestored, allowed]);

  const handleRestore = (row) => {
    if (!window.confirm(`پرونده «${row.customer_name}» احیا شود و به لیست فعال بازگردد؟`)) return;
    setRestoringId(row.id);
    restoreDeletedLead(row.id)
      .then(() => {
        notify(`پرونده «${row.customer_name}» احیا شد.`, "success");
        setRows((prev) =>
          prev.map((r) => (r.id === row.id ? { ...r, restored_at: new Date().toISOString() } : r))
        );
      })
      .catch((err) => {
        const msg = getErrorMessage(err, "احیای پرونده با خطا مواجه شد.");
        notify(msg, "error");
      })
      .finally(() => setRestoringId(null));
  };

  const clearFilters = () => {
    setSearch("");
    setDeletedById("");
    setOwnerId("");
    setDateFrom("");
    setDateTo("");
    setIncludeRestored(true);
  };

  const hasActiveFilters = deletedById || ownerId || dateFrom || dateTo || !includeRestored;

  if (!allowed) {
    return (
      <AppShell>
        <AccessDenied />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="deleted-leads-container">
        <header className="deleted-leads-header">
          <div className="deleted-leads-header__title">
            <Trash2 size={20} />
            <h1>لیدهای حذف‌شده</h1>
          </div>
          <p className="deleted-leads-header__subtitle">
            ممیزی حذف: چه کسی، چه زمانی، کدام پرونده را حذف کرد — به‌همراه امکان احیا.
          </p>
        </header>

        <div className="deleted-leads-toolbar">
          <div className="leads-search">
            <Search size={16} className="leads-search__icon" />
            <input
              className="leads-search__input"
              type="search"
              placeholder="جستجوی نام مشتری یا موبایل…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          <button
            className={`dl-filter-toggle ${hasActiveFilters ? "dl-filter-toggle--active" : ""}`}
            onClick={() => setFiltersOpen((v) => !v)}
          >
            <span>فیلترها</span>
            {hasActiveFilters && <span className="dl-filter-toggle__dot" />}
            <ChevronDown size={14} style={{ transform: filtersOpen ? "rotate(180deg)" : "none" }} />
          </button>
        </div>

        {filtersOpen && (
          <div className="dl-filters-panel">
            <div className="dl-filter-field">
              <label><UserIcon size={13} /> حذف‌شده توسط</label>
              <select value={deletedById} onChange={(e) => setDeletedById(e.target.value)}>
                <option value="">همه</option>
                {teamUsers.map((u) => (
                  <option key={u.id} value={u.id}>{u.full_name}</option>
                ))}
              </select>
            </div>

            <div className="dl-filter-field">
              <label><UserIcon size={13} /> مالک اصلی پرونده</label>
              <select value={ownerId} onChange={(e) => setOwnerId(e.target.value)}>
                <option value="">همه</option>
                {teamUsers.map((u) => (
                  <option key={u.id} value={u.id}>{u.full_name}</option>
                ))}
              </select>
            </div>

            <div className="dl-filter-field">
              <label><Calendar size={13} /> از تاریخ</label>
              <JalaliDatePicker clearable value={dateFrom} onChange={setDateFrom} placeholder="همه" />
            </div>

            <div className="dl-filter-field">
              <label><Calendar size={13} /> تا تاریخ</label>
              <JalaliDatePicker clearable value={dateTo} onChange={setDateTo} placeholder="همه" />
            </div>

            <label className="dl-filter-checkbox">
              <input
                type="checkbox"
                checked={includeRestored}
                onChange={(e) => setIncludeRestored(e.target.checked)}
              />
              <span>شامل موارد احیاشده</span>
            </label>

            {hasActiveFilters && (
              <button className="dl-filter-clear" onClick={clearFilters}>
                <X size={13} /> پاک‌کردن فیلترها
              </button>
            )}
          </div>
        )}

        {error && <div className="alert-banner alert-banner--error">{error}</div>}

        {loading && (
          <div className="dash-skeleton">
            <div className="skeleton" style={{ height: 64 }} />
            <div className="skeleton" style={{ height: 64 }} />
            <div className="skeleton" style={{ height: 64 }} />
          </div>
        )}

        {!loading && !error && (
          rows.length ? (
            <InfiniteScroll hasMore={rows.length < total} loading={loadingMore} onReachEnd={() => load(true)}>
              <div className="dl-list">
                {rows.map((row) => (
                  <div key={row.id} className={`dl-row ${row.restored_at ? "dl-row--restored" : ""}`}>
                    <div className="dl-row__main">
                      <div className="dl-row__customer">
                        <span className="dl-row__name">{row.customer_name}</span>
                        <span className="dl-row__mobile" dir="ltr">{row.mobile}</span>
                      </div>
                      <div className="dl-row__meta">
                        <span className="dl-row__badge">{statusLabel(row.previous_status)}</span>
                        {row.sale_amount ? <span className="dl-row__amount">{fmtRial(row.sale_amount)}</span> : null}
                        {row.invoice_number && <span className="dl-row__invoice">#{row.invoice_number}</span>}
                      </div>
                    </div>

                    <div className="dl-row__audit">
                      <div className="dl-row__audit-line">
                        <span className="dl-row__audit-label">حذف‌شده توسط</span>
                        <span className="dl-row__audit-value">{row.deleted_by_full_name || `#${row.deleted_by_id}`}</span>
                      </div>
                      <div className="dl-row__audit-line">
                        <span className="dl-row__audit-label">مالک اصلی</span>
                        <span className="dl-row__audit-value">{row.owner_full_name || "—"}</span>
                      </div>
                      <div className="dl-row__audit-line">
                        <span className="dl-row__audit-label">زمان حذف</span>
                        <span className="dl-row__audit-value">{formatDateTime(row.deleted_at)}</span>
                      </div>
                    </div>

                    <div className="dl-row__actions">
                      {row.restored_at ? (
                        <span className="dl-row__restored-tag">
                          احیاشده در {formatDateTime(row.restored_at)}
                        </span>
                      ) : (
                        <button
                          className="dl-restore-btn"
                          disabled={restoringId === row.id}
                          onClick={() => handleRestore(row)}
                        >
                          {restoringId === row.id ? (
                            <Loader2 size={14} className="spin" />
                          ) : (
                            <RotateCcw size={14} />
                          )}
                          <span>احیا</span>
                        </button>
                      )}
                      {row.restored_at ? (
                        <Link to={`/leads/${row.lead_id}`} className="dl-row__link">
                          مشاهده‌ی پرونده
                        </Link>
                      ) : (
                        <button
                          type="button"
                          className="dl-row__link"
                          onClick={() => setViewing(row)}
                        >
                          مشاهده‌ی جزئیات
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              {loadingMore && <div className="dl-loading-more"><Loader2 size={16} className="spin" /></div>}
            </InfiniteScroll>
          ) : (
            <div className="dl-empty">
              <Inbox size={28} strokeWidth={1.6} />
              <p>هیچ لید حذف‌شده‌ای با این فیلترها یافت نشد.</p>
            </div>
          )
        )}
      </div>

      {viewing && (
        <DeletedLeadDetailModal
          auditId={viewing.id}
          summary={viewing}
          onClose={() => setViewing(null)}
          onRestore={(row) => { setViewing(null); handleRestore(row); }}
        />
      )}
    </AppShell>
  );
}
