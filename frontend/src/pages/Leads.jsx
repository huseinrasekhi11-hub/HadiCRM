import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Search, Plus, Phone, Clock, MoveRight, StickyNote, Inbox, Users, Copy,
} from "lucide-react";
import {
  searchLeadsPaged, getPipelineCounts, updateLeadStatus, createLeadActivity,
} from "../api/client";
import { useToast } from "../components/Toast";
import AppShell from "../components/AppShell";
import HealthBadge from "../components/HealthBadge";
import NewLeadModal from "../components/NewLeadModal";
import LogActionModal from "../components/LogActionModal";
import StatusChangeModal from "../components/StatusChangeModal";
import InfiniteScroll from "../components/InfiniteScroll";
import { SkeletonList } from "../components/Skeleton";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { STATUS_ORDER, statusLabel, statusColor, WON_STATUS, LOST_STATUS } from "../leadStatus";
import "./Leads.css";
import { useModalBehavior } from "../hooks/useModalBehavior";

const PAGE_SIZE = 20;

const SMART_FILTERS = [
  { value: "", label: "همه" },
  { value: "open", label: "پرونده‌های باز" },
  { value: "today_followup", label: "پیگیری امروز" },
  { value: "overdue", label: "عقب‌افتاده" },
  { value: "no_activity", label: "بدون پیگیری" },
  { value: "critical", label: "بحرانی" },
  { value: "escalated", label: "ارجاع‌شده" },
];

function relativeFollowUp(iso) {
  const diffMs = new Date(iso).getTime() - Date.now();
  const overdue = diffMs < 0;
  const hours = Math.abs(diffMs) / 3600000;
  let text;
  if (hours < 1) text = overdue ? "دقایقی پیش" : "تا ساعاتی دیگر";
  else if (hours < 24) text = `${Math.round(hours)} ساعت ${overdue ? "پیش" : "دیگر"}`;
  else text = `${Math.round(hours / 24)} روز ${overdue ? "پیش" : "دیگر"}`;
  return { text, overdue };
}

/* --- Stage stepper: orientation + one-tap stage filtering --- */
function StageStepper({ pipeline, activeStage, onSelect }) {
  return (
    <div className="stage-stepper" role="tablist" aria-label="مراحل قیف فروش">
      <button
        className={`stage-step ${activeStage === null ? "stage-step--active" : ""}`}
        onClick={() => onSelect(null)}
      >
        <span className="stage-step__label">کل پرونده‌ها</span>
        <span className="stage-step__count">{pipeline.total}</span>
      </button>
      {pipeline.stages.map((stage) => (
        <button
          key={stage.status}
          className={`stage-step ${activeStage === stage.status ? "stage-step--active" : ""}`}
          style={{ "--stage-color": statusColor(stage.status) }}
          onClick={() => onSelect(activeStage === stage.status ? null : stage.status)}
        >
          <span className="stage-step__dot" />
          <span className="stage-step__label">{statusLabel(stage.status)}</span>
          <span className="stage-step__count">{stage.count}</span>
        </button>
      ))}
    </div>
  );
}

/* --- One lead row: identity + state + call/log/move/open --- */
function LeadRow({ lead, onLog, onMove, onOpen, onOpenDuplicates }) {
  const color = statusColor(lead.status);
  const followUp = lead.next_follow_up ? relativeFollowUp(lead.next_follow_up) : null;
  return (
    <div className="lead-card" onClick={onOpen}>
      <div className="lead-card__bar" style={{ background: color }} />
      <div className="lead-card__body">
        <div className="lead-card__top">
          <span className="lead-card__name">{lead.customer_name}</span>
          <span className="lead-card__status-wrap">
            {(lead.duplicate_count || 0) > 0 && (
              <button
                className="lead-dup-badge"
                title={`${lead.duplicate_count} ثبت تکراری — مشاهده`}
                onClick={(e) => { e.stopPropagation(); onOpenDuplicates(lead); }}
              >
                <Copy size={11} /> ×{lead.duplicate_count}
              </button>
            )}
            <span className="lead-card__status" style={{ color }}>{statusLabel(lead.status)}</span>
          </span>
        </div>
        <div className="lead-card__meta">
          <span className="lead-card__mobile">{lead.mobile}</span>
          {lead.health && <HealthBadge health={lead.health} size="md" />}
          {followUp && (
            <span className={`lead-card__followup ${followUp.overdue ? "lead-card__followup--overdue" : ""}`}>
              <Clock size={11} /> {followUp.text}
            </span>
          )}
          {lead.need && <span className="lead-card__need">{lead.need}</span>}
        </div>
      </div>
      <div className="lead-card__actions" onClick={(e) => e.stopPropagation()}>
        <a className="lead-action lead-action--call" href={`tel:${lead.mobile}`} aria-label="تماس">
          <Phone size={18} />
        </a>
        <button className="lead-action" onClick={() => onLog(lead)} aria-label="ثبت اقدام">
          <StickyNote size={18} />
        </button>
        <button className="lead-action" onClick={() => onMove(lead)} aria-label="تغییر مرحله">
          <MoveRight size={18} />
        </button>
      </div>
    </div>
  );
}

/* --- Move-to-stage modal (tap-to-advance) --- */
function MoveStageModal({ lead, onClose, onMove }) {
  const dialogRef = useModalBehavior(onClose);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" ref={dialogRef} role="dialog" aria-modal="true"
        onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <div className="modal__icon-bg"><MoveRight size={20} /></div>
          <div>
            <h2 className="modal__title">تغییر مرحله</h2>
            <p className="modal__subtitle">{lead.customer_name} — {statusLabel(lead.status)}</p>
          </div>
        </div>
        <div className="move-stage-list">
          {STATUS_ORDER.filter((s) => s !== lead.status).map((s) => (
            <button
              key={s}
              className="move-stage-item"
              style={{ "--stage-color": statusColor(s) }}
              onClick={() => onMove(s)}
            >
              <span className="move-stage-item__dot" />
              {statusLabel(s)}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function Leads() {
  const navigate = useNavigate();
  const notify = useToast();
  const [searchParams, setSearchParams] = useSearchParams();

  const [search, setSearch] = useState("");

  const [filter, setFilter] = useState(() => {
    const urlStage = searchParams.get("stage");
    if (urlStage) return { kind: "stage", value: urlStage };
    const urlFilter = searchParams.get("filter");
    if (urlFilter && SMART_FILTERS.some((f) => f.value === urlFilter)) {
      return { kind: "smart", value: urlFilter };
    }
    return { kind: "smart", value: "open" };
  });

  // پیش‌تر انتخاب فیلتر/مرحله فقط در state نگه داشته می‌شد و در URL
  // منعکس نمی‌شد؛ با رفرش صفحه یا اشتراک‌گذاری لینک، فیلتر انتخابی
  // کاربر بی‌صدا از بین می‌رفت. حالا هر تغییرِ فیلتر در query params
  // هم نوشته می‌شود تا state اولیه (بالا) با رفرش دوباره از همان‌جا
  // بازسازی شود.
  useEffect(() => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete("filter");
        next.delete("stage");
        if (filter.kind === "stage" && filter.value) {
          next.set("stage", filter.value);
        } else if (filter.kind === "smart" && filter.value) {
          next.set("filter", filter.value);
        }
        return next;
      },
      { replace: true }
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  const [leads, setLeads] = useState([]);
  const [total, setTotal] = useState(0);
  const [pipeline, setPipeline] = useState({ total: 0, stages: [] });
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");

  const [showNewLead, setShowNewLead] = useState(false);
  const [logLead, setLogLead] = useState(null);
  const [moveLead, setMoveLead] = useState(null);
  const [pendingClose, setPendingClose] = useState(null);
  const [pipelineError, setPipelineError] = useState(false);

  const debounced = useDebouncedValue(search.trim(), 300);

  function queryParams(skip) {
    const params = { search: debounced || undefined, skip, limit: PAGE_SIZE };
    if (filter.kind === "stage") params.status = filter.value;
    else if (filter.value) params.smartFilter = filter.value;
    return params;
  }

  // شناسه‌ی درخواست جاری: پاسخ‌های قدیمی که دیرتر می‌رسند نباید
  // نتیجه‌ی جست‌وجوی جدیدتر را بازنویسی کنند (race condition).
  const requestIdRef = useRef(0);

  // تعداد فعلی لیدهای بارگذاری‌شده، برای محاسبه‌ی skip در صفحه‌بندی.
  // با ref نگه داشته می‌شود (نه مستقیم از state خوانده می‌شود) تا
  // خودِ تابع load در هر رندر از نو ساخته نشود — در غیر این صورت
  // IntersectionObserver داخل InfiniteScroll با هر تغییر state (مثلاً
  // هر حرفی که در جست‌وجو تایپ می‌شود) از نو ساخته می‌شد.
  const leadsLengthRef = useRef(0);
  useEffect(() => {
    leadsLengthRef.current = leads.length;
  }, [leads.length]);

  const load = useCallback(async (append = false) => {
    const requestId = ++requestIdRef.current;
    if (append) setLoadingMore(true);
    else setLoading(true);
    setError("");
    try {
      const skip = append ? leadsLengthRef.current : 0;
      const [page, pipe] = await Promise.all([
        searchLeadsPaged(queryParams(skip)),
        append
          ? null
          : getPipelineCounts({ search: debounced || undefined }).catch(() => "error"),
      ]);
      // پاسخ کهنه است؛ نادیده گرفته می‌شود
      if (requestId !== requestIdRef.current) return;

      if (pipe === "error") {
        // پیش از این خطا کاملاً بلعیده می‌شد و نوار مراحل بی‌صدا صفر
        // نشان می‌داد؛ حالا دست‌کم به کاربر اطلاع داده می‌شود.
        setPipelineError(true);
      } else if (pipe) {
        setPipelineError(false);
        setPipeline(pipe);
      }
      setTotal(page.total);
      setLeads((prev) => (append ? [...prev, ...page.items] : page.items));
    } catch {
      if (requestId !== requestIdRef.current) return;
      setError("بارگذاری لیدها با خطا مواجه شد.");
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced, filter]);

  useEffect(() => {
    load(false);
  }, [load]);

  const handleReachEnd = useCallback(() => {
    load(true);
  }, [load]);

  function selectSmartFilter(value) {
    setFilter({ kind: "smart", value });
  }

  function selectStage(status) {
    setFilter(status ? { kind: "stage", value: status } : { kind: "smart", value: "" });
  }

  async function commitStatusChange(lead, targetStatus, extra = {}) {
    const previous = lead.status;
    setLeads((prev) => prev.map((l) => (l.id === lead.id ? { ...l, status: targetStatus } : l)));
    try {
      const updated = await updateLeadStatus(lead.id, targetStatus, extra);
      setLeads((prev) => prev.map((l) => (l.id === lead.id ? updated : l)));
      notify(`به «${statusLabel(targetStatus)}» منتقل شد.`, "success");
      getPipelineCounts({ search: debounced || undefined }).then(setPipeline).catch(() => {});
    } catch {
      setLeads((prev) => prev.map((l) => (l.id === lead.id ? { ...l, status: previous } : l)));
      notify("تغییر وضعیت با خطا مواجه شد.", "error");
    }
  }

  function handleMove(lead, targetStatus) {
    setMoveLead(null);
    if (targetStatus === WON_STATUS || targetStatus === LOST_STATUS) {
      setPendingClose({ lead, targetStatus });
    } else {
      commitStatusChange(lead, targetStatus);
    }
  }

  async function handleLogSubmit(payload) {
    if (!logLead) return;
    try {
      await createLeadActivity(logLead.id, payload);
      notify("اقدام ثبت شد.", "success");
      setLogLead(null);
      load(false);
    } catch {
      notify("ثبت اقدام با خطا مواجه شد.", "error");
    }
  }

  const activeStage = filter.kind === "stage" ? filter.value : null;

  return (
    <AppShell>
      <div className="leads-page">
        {/* Toolbar */}
        <header className="leads-toolbar">
          <div className="leads-search">
            <Search size={16} className="leads-search__icon" />
            <input
              className="leads-search__input"
              type="search"
              placeholder="جستجوی نام، موبایل یا نیاز مشتری…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <button className="btn-primary" onClick={() => setShowNewLead(true)}>
            <Plus size={16} strokeWidth={2.5} /> لید جدید
          </button>
        </header>

        {/* Smart filter chips */}
        <div className="smart-chips">
          {SMART_FILTERS.map((f) => (
            <button
              key={f.value}
              className={`chip ${filter.kind === "smart" && filter.value === f.value ? "chip--active" : ""}`}
              onClick={() => selectSmartFilter(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* Stage stepper (counts from ONE request) */}
        {pipelineError && (
          <div className="alert-banner alert-banner--warning">
            شمارش مراحل قیف بارگذاری نشد؛ اعداد ممکن است به‌روز نباشند.
          </div>
        )}
        <StageStepper pipeline={pipeline} activeStage={activeStage} onSelect={selectStage} />

        {/* List */}
        <div className="leads-list">
          {error && <div className="alert-banner alert-banner--error">{error}</div>}

          {loading ? (
            <SkeletonList rows={5} rowHeight={76} />
          ) : leads.length === 0 ? (
            <div className="empty-state">
              <Inbox size={28} className="empty-state__icon" />
              <h3 className="empty-state__title">پرونده‌ای یافت نشد</h3>
              <p className="empty-state__subtitle">
                فیلترها را تغییر دهید یا یک لید جدید ثبت کنید.
              </p>
            </div>
          ) : (
            <>
              <div className="leads-list__summary">
                <Users size={13} />
                نمایش {leads.length} از {total} پرونده
              </div>
              <InfiniteScroll hasMore={leads.length < total} loading={loadingMore} onReachEnd={handleReachEnd}>
                {leads.map((lead) => (
                  <LeadRow
                    key={lead.id}
                    lead={lead}
                    onLog={setLogLead}
                    onMove={setMoveLead}
                    onOpen={() => navigate(`/leads/${lead.id}`)}
                    onOpenDuplicates={(l) => navigate(`/leads/${l.id}?tab=duplicates`)}
                  />
                ))}
              </InfiniteScroll>
            </>
          )}
        </div>
      </div>

      {/* Modals */}
      {showNewLead && (
        <NewLeadModal
          onClose={() => setShowNewLead(false)}
          onCreated={(lead) => {
            setShowNewLead(false);
            navigate(`/leads/${lead.id}`);
          }}
        />
      )}
      {logLead && <LogActionModal onClose={() => setLogLead(null)} onSubmit={handleLogSubmit} />}
      {moveLead && (
        <MoveStageModal
          lead={moveLead}
          onClose={() => setMoveLead(null)}
          onMove={(target) => handleMove(moveLead, target)}
        />
      )}
      {pendingClose && (
        <StatusChangeModal
          targetStatus={pendingClose.targetStatus}
          onClose={() => setPendingClose(null)}
          onSubmit={async (extra) => {
            await commitStatusChange(pendingClose.lead, pendingClose.targetStatus, extra);
            setPendingClose(null);
          }}
        />
      )}
    </AppShell>
  );
}
