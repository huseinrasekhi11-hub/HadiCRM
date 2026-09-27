import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Phone, MessageCircle, Activity, CalendarClock, Pencil, UserCog, Trash2,
  Loader2, AlertTriangle, Plus, FileText, Upload, Copy, Layers,
  History, ListChecks, DollarSign, Check,
} from "lucide-react";
import {
  getLead, createLeadActivity, getLeadTasks, createLeadTask,
  updateLeadTaskStatus, getLeadAttachments, uploadLeadAttachment,
  updateLeadStatus, assignLead, getAssignableUsers, downloadAttachment, deleteLead,
  updateLead, setLeadFollowUp, getLeadSaleItems, createLeadSaleItem,
  getProducts, getLeadRelatedLeads,
} from "../api/client";
import { useToast } from "../hooks/useToast";
import { usePermissions } from "../hooks/usePermissions";
import AppShell from "../components/AppShell";
import HealthBadge from "../components/HealthBadge";
import LogActionModal from "../components/LogActionModal";
import StatusChangeModal from "../components/StatusChangeModal";
import StagePath from "../components/StagePath";
import FollowUpModal from "../components/FollowUpModal";
import AddSaleItemModal from "../components/AddSaleItemModal";
import DuplicateCenter from "../components/DuplicateCenter";
import LeadHistory from "../components/LeadHistory";
import AssignModal from "../components/AssignModal";
import { statusLabel, statusColor, taskStatusLabel, WON_STATUS, LOST_STATUS } from "../leadStatus";
import "./LeadDetail.css";
import { useModalBehavior } from "../hooks/useModalBehavior";
import JalaliDatePicker from "../components/JalaliDatePicker";
import { getErrorMessage } from "../utils/apiError";

const fmtDate = (iso) => (iso ? new Intl.DateTimeFormat("fa-IR-u-ca-persian", { dateStyle: "medium" }).format(new Date(iso)) : "—");
const fmtDateTime = (iso) => (iso ? new Intl.DateTimeFormat("fa-IR-u-ca-persian", { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso)) : "—");
const initials = (name) => (name || "؟").trim().split(/\s+/).slice(0, 2).map((p) => p[0]).join("");
const isOverdue = (iso) => Boolean(iso) && new Date(iso).getTime() < Date.now();

/* ---------- Edit Lead Modal ---------- */
function EditLeadModal({ lead, onClose, onSubmit }) {
  const [formData, setFormData] = useState({
    customer_name: lead.customer_name || "",
    mobile: lead.mobile || "",
    source: lead.source || "",
    need: lead.need || "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const dialogRef = useModalBehavior(onClose);
  const set = (key) => (e) => setFormData((p) => ({ ...p, [key]: e.target.value }));
  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try { await onSubmit(formData); }
    catch (err) { setError(getErrorMessage(err, "بروزرسانی با خطا مواجه شد.")); setSubmitting(false); }
  }
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" ref={dialogRef} role="dialog" aria-modal="true"
        onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <div className="modal__icon-bg"><Pencil size={20} /></div>
          <div>
            <h2 className="modal__title">ویرایش اطلاعات مشتری</h2>
            <p className="modal__subtitle">نام، موبایل، منبع و نیاز پرونده.</p>
          </div>
        </div>
        <form onSubmit={handleSubmit}>
          <label className="field">
            <span className="field__label">نام مشتری <span className="text-red-500">*</span></span>
            <input className="premium-input" value={formData.customer_name} onChange={set("customer_name")} required autoFocus />
          </label>
          <label className="field">
            <span className="field__label">موبایل <span className="text-red-500">*</span></span>
            <input className="premium-input premium-input--ltr" inputMode="tel" value={formData.mobile} onChange={set("mobile")} required />
          </label>
          <label className="field">
            <span className="field__label">منبع ورودی</span>
            <input className="premium-input" value={formData.source} onChange={set("source")} />
          </label>
          <label className="field">
            <span className="field__label">شرح نیاز</span>
            <textarea className="premium-input" rows={3} value={formData.need} onChange={set("need")} />
          </label>
          {error && <div className="form-error-banner">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>انصراف</button>
            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting ? <Loader2 size={16} className="spin" /> : "ذخیره تغییرات"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ---------- Quick note composer ---------- */
function QuickComposer({ onSubmit, onOpenFull }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault();
    if (!note.trim()) return;
    setBusy(true);
    await onSubmit(note);
    setNote("");
    setBusy(false);
  }
  return (
    <form className="quick-composer" onSubmit={submit}>
      <input className="premium-input" placeholder="یادداشت سریع بنویسید…" value={note} onChange={(e) => setNote(e.target.value)} />
      <div className="quick-composer__actions">
        <button type="button" className="btn-ghost" onClick={onOpenFull}><Plus size={14} /> ثبت اقدام کامل</button>
        <button type="submit" className="btn-primary" disabled={!note.trim() || busy}>
          {busy ? <Loader2 size={14} className="spin" /> : "ثبت"}
        </button>
      </div>
    </form>
  );
}

/* ======================================================================== */
export default function LeadDetail() {
  const { leadId } = useParams();
  const navigate = useNavigate();
  const notify = useToast();
  const { canAssignAnyLead, canModifyLead, canDeleteLead, isOwner, isAdmin } = usePermissions();

  const [lead, setLead] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("activity");
  const [historyVersion, setHistoryVersion] = useState(0);

  const [tasks, setTasks] = useState([]);
  const [attachments, setAttachments] = useState([]);
  const [saleItems, setSaleItems] = useState([]);
  const [products, setProducts] = useState([]);
  const [relatedLeads, setRelatedLeads] = useState([]);
  const [assignableUsers, setAssignableUsers] = useState([]);

  const [pendingStatus, setPendingStatus] = useState(null);
  const [showLogAction, setShowLogAction] = useState(false);
  const [showEditLead, setShowEditLead] = useState(false);
  const [showAssign, setShowAssign] = useState(false);
  const [showFollowUp, setShowFollowUp] = useState(false);
  const [showAddSaleItem, setShowAddSaleItem] = useState(false);

  const loadCore = useCallback(() => getLead(leadId).then(setLead), [leadId]);
  const bumpHistory = () => setHistoryVersion((v) => v + 1);

  // Navigating to another lead resets the page during render (the
  // documented "adjust state when a prop changes" pattern) instead of in an
  // effect, which would first paint the previous lead's data again.
  const [loadKey, setLoadKey] = useState(leadId);
  if (loadKey !== leadId) {
    setLoadKey(leadId);
    setLoading(true);
    setError("");
  }

  useEffect(() => {
    Promise.all([
      loadCore(),
      getLeadTasks(leadId).then(setTasks).catch(() => setTasks([])),
      getLeadAttachments(leadId).then(setAttachments).catch(() => setAttachments([])),
      getLeadSaleItems(leadId).then(setSaleItems).catch(() => setSaleItems([])),
      getProducts().then(setProducts).catch(() => setProducts([])),
      getLeadRelatedLeads(leadId).then(setRelatedLeads).catch(() => setRelatedLeads([])),
    ])
      .catch((err) => {
        // A 404 here specifically means the lead is gone or no longer
        // belongs to this user (reassigned, referred elsewhere, deleted) —
        // distinct from a real connectivity failure, so it gets its own
        // message rather than the generic one.
        if (err?.response?.status === 404) {
          setError("این پرونده دیگر در دسترس شما نیست. ممکن است به کارشناس دیگری ارجاع شده یا حذف شده باشد.");
        } else {
          setError("دریافت اطلاعات پرونده با خطا مواجه شد.");
        }
      })
      .finally(() => setLoading(false));
  }, [leadId, loadCore, loadKey]);

  useEffect(() => {
    // Fetch assignable users if the user has permission to assign
    if (canAssignAnyLead || (lead && isOwner(lead.owner_id))) {
      getAssignableUsers().then(setAssignableUsers).catch(() => {});
    }
  }, [canAssignAnyLead, lead, isOwner]);

  const showDuplicatesTab = !!lead && ((lead.duplicate_count || 0) > 0 || relatedLeads.length > 0);
  const effectiveTab = activeTab === "duplicates" && !showDuplicatesTab ? "activity" : activeTab;

  // Computed Permissions for this specific lead
  const canAssign = lead ? (canAssignAnyLead || isOwner(lead.owner_id)) : false;
  // قفل فاکتور: صدور فاکتور یک سند مالی است. پس از صدور، اصلاح آن —
  // شامل مبلغ، اقلام فروش و مرحله‌ی پرونده — فقط از عهده‌ی مدیر سیستم
  // برمی‌آید. کارشناس فروش (حتی مالک پرونده که خودش فاکتور را صادر کرده)
  // و مدیران میانی از این نقطه به بعد فقط خواننده هستند.
  //
  // پیش از این، هر نقشِ «ناظر» (هر کسی با canViewAllLeads که مالک نبود)
  // می‌توانست فاکتور قفل‌شده را تغییر دهد و در مقابل، فاکتورِ خودِ ادمین
  // برای او قفل می‌ماند. هر دو رفتار اصلاح شد.
  const isInvoiceLocked = Boolean(lead?.is_invoice_locked);
  const canEditFactor = isAdmin;
  const canEdit = lead
    ? canModifyLead(lead.owner_id) && (!isInvoiceLocked || canEditFactor)
    : false;
  const canDelete = lead ? canDeleteLead(lead.owner_id) : false;

  /* ---------- Stage change ---------- */
  const handleStageSelect = (target) => {
    if (isInvoiceLocked && !canEditFactor) {
      notify(
        "فاکتور این پرونده صادر شده است و تغییر آن فقط از طریق مدیر سیستم ممکن است.",
        "error"
      );
      return;
    }
    if (target === WON_STATUS || target === LOST_STATUS) setPendingStatus(target);
    else commitStatusChange(target);
  };
  const commitStatusChange = async (target, extra = {}) => {
    const prev = lead.status;
    setLead((l) => ({ ...l, status: target }));
    try {
      const updated = await updateLeadStatus(leadId, target, extra);
      setLead(updated);
      notify(`به «${statusLabel(target)}» منتقل شد.`, "success");
      getLeadSaleItems(leadId).then(setSaleItems).catch(() => {});
      bumpHistory();
    } catch (err) {
      if (err?.response?.status === 403) {
        notify(
          err.response.data?.detail || "این پرونده قفل شده و قابل ویرایش نیست.",
          "error"
        );
      }
      setLead((l) => ({ ...l, status: prev }));
      notify("تغییر وضعیت با خطا مواجه شد.", "error");
    }
  };

  /* ---------- Activity logging ---------- */
  const handleLogSubmit = async (payload) => {
    try {
      await createLeadActivity(leadId, payload);
      setShowLogAction(false);
      notify("اقدام ثبت شد.", "success");
      bumpHistory();
      loadCore().catch(() => {});
    } catch {
      notify("ثبت اقدام با خطا مواجه شد.", "error");
    }
  };
  const handleQuickNote = async (note) => {
    try {
      await createLeadActivity(leadId, { activity_type: "note", title: "یادداشت", description: note });
      notify("یادداشت ثبت شد.", "success");
      bumpHistory();
      loadCore().catch(() => {});
    } catch {
      notify("ثبت یادداشت با خطا مواجه شد.", "error");
    }
  };

  /* ---------- Tasks ---------- */
  const handleTaskAdd = async (payload) => {
    try {
      const task = await createLeadTask(leadId, payload);
      setTasks((prev) => [task, ...prev]);
      notify("وظیفه ثبت شد.", "success");
    } catch { notify("ثبت وظیفه با خطا مواجه شد.", "error"); }
  };
  const handleTaskToggle = async (task) => {
    const next = task.status === "done" ? "pending" : "done";
    setTasks((prev) => prev.map((t) => (t.id === task.id ? { ...t, status: next } : t)));
    try {
      await updateLeadTaskStatus(leadId, task.id, next);
      if (next === "done") notify("وظیفه انجام شد.", "success");
    } catch {
      setTasks((prev) => prev.map((t) => (t.id === task.id ? { ...t, status: task.status } : t)));
      notify("بروزرسانی وظیفه با خطا مواجه شد.", "error");
    }
  };

  /* ---------- Attachments ---------- */
  const handleUpload = async (file) => {
    try {
      const attachment = await uploadLeadAttachment(leadId, file);
      setAttachments((prev) => [attachment, ...prev]);
      notify("فایل آپلود شد.", "success");
      bumpHistory();
    } catch { notify("آپلود فایل با خطا مواجه شد.", "error"); }
  };

  /* ---------- Sale items ---------- */
  const handleAddSaleItem = async (payload) => {
    await createLeadSaleItem(leadId, payload);
    setShowAddSaleItem(false);
    notify("قلم فروش ثبت شد.", "success");
    getLeadSaleItems(leadId).then(setSaleItems).catch(() => {});
    loadCore().catch(() => {});
    bumpHistory();
  };

  /* ---------- Follow-up / assign / edit / delete ---------- */
  const handleFollowUp = async (iso) => {
    const updated = await setLeadFollowUp(leadId, iso);
    setLead(updated);
    setShowFollowUp(false);
    notify("زمان پیگیری تنظیم شد.", "success");
    bumpHistory();
  };
  const handleAssign = async (ownerId, note) => {
    const updated = await assignLead(leadId, ownerId, note);
    setLead(updated);
    setShowAssign(false);
    notify("پرونده ارجاع داده شد.", "success");
    bumpHistory();
  };
  const handleEditLead = async (payload) => {
    const updated = await updateLead(leadId, payload);
    setLead(updated);
    setShowEditLead(false);
    notify("اطلاعات مشتری بروزرسانی شد.", "success");
  };
  const handleDelete = async () => {
    if (!window.confirm(
      `پرونده «${lead.customer_name}» حذف شود؟ تاریخچه و اقدام‌های ثبت‌شده باقی می‌مانند و مدیر می‌تواند آن را بازگردانی کند.`
    )) return;
    try {
      await deleteLead(leadId);
      notify("پرونده حذف شد.", "success");
      navigate("/leads");
    } catch { notify("حذف پرونده با خطا مواجه شد.", "error"); }
  };

  if (loading) {
    return (
      <AppShell>
        <div className="ws-skeleton">
          <div className="skeleton" style={{ height: 180 }} />
          <div className="skeleton" style={{ height: 400 }} />
        </div>
      </AppShell>
    );
  }
  if (error || !lead) {
    return (
      <AppShell>
        <div className="ws-error-state">
          <div className="alert-banner alert-banner--error">{error || "پرونده پیدا نشد."}</div>
          <button type="button" className="ws-back ws-back--button" onClick={() => navigate(-1)}>
            بازگشت
          </button>
        </div>
      </AppShell>
    );
  }

  const color = statusColor(lead.status);
  const TABS = [
    { id: "activity", label: "تاریخچه و فعالیت‌ها", icon: History },
    { id: "tasks", label: "وظایف", icon: ListChecks, badge: tasks.length },
    { id: "sales", label: "فروش", icon: DollarSign, badge: saleItems.length },
    { id: "files", label: "فایل‌ها", icon: FileText, badge: attachments.length },
    { id: "details", label: "جزئیات", icon: Layers },
    ...(showDuplicatesTab
      ? [{ id: "duplicates", label: "ثبت‌های تکراری", icon: Copy, badge: lead.duplicate_count || 0 }]
      : []),
  ];

  return (
    <AppShell>
      <div className="ws">
        <button className="ws-back" onClick={() => navigate("/leads")}>
          بازگشت به لیست پرونده‌ها
        </button>

        {lead.is_escalated && (
          <div className="alert-banner alert-banner--warning">
            <AlertTriangle size={16} /> این پرونده به دلیل عدم فعالیت به مدیر ارجاع اضطراری شده است.
          </div>
        )}

        {/* ---------- Workspace Header ---------- */}
        <header className="ws-header card">
          <div className="ws-header__top">
            <div className="ws-identity">
              <div className="ws-avatar" style={{ "--stage-color": color }} aria-hidden="true">
                {initials(lead.customer_name)}
              </div>
              <div className="ws-identity__info">
                <h1 className="ws-identity__name">{lead.customer_name}</h1>
                <div className="ws-identity__meta">
                  <span className="ws-identity__mobile">{lead.mobile}</span>
                  {lead.source && <span className="ws-meta-dot">•</span>}
                  {lead.source && <span>{lead.source}</span>}
                </div>
              </div>
            </div>
            <div className="ws-header__badges">
              <span className="badge ws-status-badge" style={{ "--stage-color": color }}>
                {statusLabel(lead.status)}
              </span>
              {lead.health && <HealthBadge health={lead.health} size="md" />}
              {(lead.duplicate_count || 0) > 0 && (
                <button className="badge badge--warning ws-dup-badge" onClick={() => setActiveTab("duplicates")}>
                  <Copy size={12} /> {lead.duplicate_count} ثبت تکراری
                </button>
              )}
            </div>
          </div>

          <StagePath
            currentStatus={lead.status}
            onSelect={handleStageSelect}
            disabled={isInvoiceLocked && !canEditFactor}
          />

          <div className="ws-header__facts">
            <div className="ws-fact">
              <span className="ws-fact__label">پیگیری بعدی</span>
              <span className={`ws-fact__value ${isOverdue(lead.next_follow_up) ? "ws-fact__value--danger" : ""}`}>
                {lead.next_follow_up ? fmtDateTime(lead.next_follow_up) : "تعیین نشده"}
              </span>
            </div>
            <div className="ws-fact">
              <span className="ws-fact__label">تاریخ ایجاد</span>
              <span className="ws-fact__value">{fmtDate(lead.created_at)}</span>
            </div>
            <div className="ws-fact">
              <span className="ws-fact__label">مبلغ فروش</span>
              <span className="ws-fact__value">
                {lead.sale_amount ? `${lead.sale_amount.toLocaleString("fa-IR")} ریال` : "—"}
              </span>
            </div>
          </div>

          <div className="ws-quick-actions">
            <a className="btn-secondary ws-action" href={`tel:${lead.mobile}`}><Phone size={16} /> تماس</a>
            <a className="btn-secondary ws-action" href={`https://wa.me/${lead.mobile.replace(/^0/, "98")}`} target="_blank" rel="noreferrer"><MessageCircle size={16} /> واتساپ</a>
            <button className="btn-primary ws-action" onClick={() => setShowLogAction(true)}><Activity size={16} /> ثبت اقدام</button>
            <button className="btn-secondary ws-action" onClick={() => setShowFollowUp(true)}><CalendarClock size={16} /> پیگیری</button>
            
            {/* ROLE-AWARE ACTIONS */}
            {canAssign && (
              <button className="btn-secondary ws-action" onClick={() => setShowAssign(true)}>
                <UserCog size={16} /> ارجاع
              </button>
            )}
            {canDelete && (
              <button className="btn-danger ws-action" onClick={handleDelete}>
                <Trash2 size={16} /> حذف
              </button>
            )}
          </div>
        </header>

        {/* ---------- Tabs ---------- */}
        <nav className="ws-tabs">
          {TABS.map(({ id, label, icon: Icon, badge }) => (
            <button key={id} className={`ws-tab ${effectiveTab === id ? "ws-tab--active" : ""}`} onClick={() => setActiveTab(id)}>
              <Icon size={16} /> {label}
              {badge > 0 && <span className="ws-tab__badge">{badge}</span>}
            </button>
          ))}
        </nav>

        <div className="ws-tab-content">
          {effectiveTab === "activity" && (
            <div className="activity-pane">
              <QuickComposer onSubmit={handleQuickNote} onOpenFull={() => setShowLogAction(true)} />
              <LeadHistory lead={lead} refreshToken={historyVersion} />
            </div>
          )}
          {effectiveTab === "tasks" && <TasksTab tasks={tasks} onToggle={handleTaskToggle} onAdd={handleTaskAdd} />}
          {effectiveTab === "sales" && (
            <SalesTab
              lead={lead}
              saleItems={saleItems}
              onAdd={() => setShowAddSaleItem(true)}
              locked={isInvoiceLocked && !canEditFactor}
            />
          )}
          {effectiveTab === "files" && <FilesTab attachments={attachments} onUpload={handleUpload} leadId={lead.id} />}
          {effectiveTab === "details" && <DetailsTab lead={lead} onEdit={() => setShowEditLead(true)} canEdit={canEdit} />}
          {effectiveTab === "duplicates" && <DuplicateCenter lead={lead} related={relatedLeads} />}
        </div>
      </div>

      {/* ---------- Modals ---------- */}
      {showLogAction && <LogActionModal onClose={() => setShowLogAction(false)} onSubmit={handleLogSubmit} />}
      {showEditLead && <EditLeadModal lead={lead} onClose={() => setShowEditLead(false)} onSubmit={handleEditLead} />}
      {showAssign && (
        <AssignModal users={assignableUsers} currentOwnerId={lead.owner_id} onClose={() => setShowAssign(false)} onSubmit={handleAssign} />
      )}
      {showFollowUp && <FollowUpModal onClose={() => setShowFollowUp(false)} onSubmit={handleFollowUp} />}
      {showAddSaleItem && <AddSaleItemModal products={products} onClose={() => setShowAddSaleItem(false)} onSubmit={handleAddSaleItem} />}
      {pendingStatus && (
        <StatusChangeModal
          targetStatus={pendingStatus}
          onClose={() => setPendingStatus(null)}
          onSubmit={async (extra) => { await commitStatusChange(pendingStatus, extra); setPendingStatus(null); }}
        />
      )}
    </AppShell>
  );
}

/* ================= Tab Components ================= */
function TasksTab({ tasks, onToggle, onAdd }) {
  const [title, setTitle] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    await onAdd({ title, due_at: new Date(dueAt).toISOString() });
    setTitle(""); setDueAt(""); setShowForm(false); setSubmitting(false);
  }
  return (
    <div className="card ws-panel">
      <div className="ws-panel__header">
        <h3 className="ws-panel__title">وظایف پرونده</h3>
        {!showForm && <button className="btn-ghost" onClick={() => setShowForm(true)}><Plus size={14} /> وظیفه جدید</button>}
      </div>
      {showForm && (
        <form className="ws-task-form" onSubmit={handleSubmit}>
          <input className="premium-input" placeholder="عنوان وظیفه…" required value={title} onChange={(e) => setTitle(e.target.value)} />
          <JalaliDatePicker withTime required value={dueAt} onChange={setDueAt} />
          <div className="ws-task-form__actions">
            <button type="button" className="btn-ghost" onClick={() => setShowForm(false)}>انصراف</button>
            <button type="submit" className="btn-primary" disabled={submitting}>ثبت</button>
          </div>
        </form>
      )}
      <div className="ws-task-list">
        {tasks.length === 0 && !showForm ? (
          <div className="empty-state"><ListChecks size={28} className="empty-state__icon" /><h3 className="empty-state__title">وظیفه‌ای ثبت نشده</h3></div>
        ) : (
          tasks.map((task, i) => {
            const done = task.status === "done";
            const overdue = !done && isOverdue(task.due_at);
            return (
              <div key={task.id} className={`ws-task-item ${done ? "ws-task-item--done" : ""}`} style={{ "--stagger": i }}>
                <button className={`ws-task-check ${done ? "ws-task-check--checked" : ""}`} onClick={() => onToggle(task)}>
                  {done && <Check size={14} strokeWidth={3} />}
                </button>
                <div className="ws-task-info">
                  <div className="ws-task-title">{task.title}</div>
                  <div className={`ws-task-meta ${overdue ? "ws-task-meta--overdue" : ""}`}>سررسید: {fmtDateTime(task.due_at)}</div>
                </div>
                <span className={`badge ${done ? "badge--success" : overdue ? "badge--danger" : "badge--neutral"}`}>{taskStatusLabel(task.status)}</span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function SalesTab({ lead, saleItems, onAdd, locked = false }) {
  const saleTotal = saleItems.reduce((sum, it) => sum + (it.amount || 0), 0);
  return (
    <div className="card ws-panel">
      <div className="ws-panel__header">
        <h3 className="ws-panel__title">اقلام فروش</h3>
        {!locked && (
          <button className="btn-primary" onClick={onAdd}><Plus size={14} /> افزودن قلم</button>
        )}
      </div>
      {locked && (
        <p className="ws-locked-note">
          فاکتور این پرونده صادر شده است. اقلام و مبلغ فروش پس از صدور
          فقط توسط مدیر سیستم قابل اصلاح هستند.
        </p>
      )}
      <div className="ws-sales-summary">
        <div className="ws-sales-summary__item"><span className="ws-fact__label">مجموع اقلام</span><span className="ws-sales-summary__value">{saleTotal.toLocaleString("fa-IR")} ریال</span></div>
        <div className="ws-sales-summary__item"><span className="ws-fact__label">مبلغ پرونده</span><span className="ws-sales-summary__value">{lead.sale_amount ? `${lead.sale_amount.toLocaleString("fa-IR")} ریال` : "—"}</span></div>
      </div>
      {saleItems.length === 0 ? (
        <div className="empty-state"><DollarSign size={28} className="empty-state__icon" /><h3 className="empty-state__title">قلم فروشی ثبت نشده</h3></div>
      ) : (
        <div className="ws-sales-list">
          {saleItems.map((item, i) => (
            <div key={item.id} className="list-row" style={{ "--stagger": i }}>
              <FileText size={18} className="ws-sales-list__icon" />
              <div className="ws-sales-list__info"><span className="ws-sales-list__name">{item.product_name || "کالا"}</span><span className="ws-sales-list__date">{fmtDate(item.created_at)}</span></div>
              <span className="ws-sales-list__amount">{item.amount.toLocaleString("fa-IR")} ریال</span>
            </div>
          ))}
        </div>
      )}
      {lead.sold_products && <div className="ws-sales-legacy"><span className="ws-fact__label">متن آزاد قدیمی:</span> {lead.sold_products}</div>}
    </div>
  );
}

function FilesTab({ attachments, onUpload, leadId }) {
  const [uploading, setUploading] = useState(false);
  async function handleFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    await onUpload(file);
    setUploading(false);
    e.target.value = "";
  }
  return (
    <div className="card ws-panel">
      <div className="ws-panel__header">
        <h3 className="ws-panel__title">فایل‌های پیوست</h3>
        <label className="btn-primary" tabIndex={0} role="button"
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.currentTarget.querySelector("input").click(); } }}>
          {uploading ? <Loader2 size={14} className="spin" /> : <Upload size={14} />} آپلود فایل
          <input type="file" hidden onChange={handleFile} disabled={uploading} />
        </label>
      </div>
      {attachments.length === 0 ? (
        <div className="empty-state"><FileText size={28} className="empty-state__icon" /><h3 className="empty-state__title">فایلی پیوست نشده</h3></div>
      ) : (
        <div className="ws-files-list">
          {attachments.map((att, i) => (
            <a key={att.id} className="list-row" href="#" rel="noreferrer" style={{ "--stagger": i }}
              onClick={(e) => { e.preventDefault(); downloadAttachment(leadId, att.id, att.file_name).catch(() => {}); }}>
              <FileText size={18} className="ws-files-list__icon" /><span className="ws-files-list__name">{att.file_name}</span><span className="ws-files-list__date">{fmtDate(att.created_at)}</span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

function DetailsTab({ lead, onEdit, canEdit }) {
  const rows = [
    { label: "نام مشتری", value: lead.customer_name },
    { label: "موبایل", value: lead.mobile, ltr: true },
    { label: "منبع ورودی", value: lead.source || "—" },
    { label: "شرح نیاز", value: lead.need || "—" },
    { label: "وضعیت", value: statusLabel(lead.status) },
    { label: "تاریخ ایجاد", value: fmtDateTime(lead.created_at) },
    { label: "آخرین به‌روزرسانی", value: fmtDateTime(lead.updated_at) },
    { label: "آخرین تماس", value: lead.last_contact_at ? fmtDateTime(lead.last_contact_at) : "—" },
    { label: "شماره فاکتور", value: lead.invoice_number || "—" },
  ];
  return (
    <div className="card ws-panel">
      <div className="ws-panel__header">
        <h3 className="ws-panel__title">جزئیات پرونده</h3>
        {canEdit && (
          <button className="btn-ghost" onClick={onEdit}><Pencil size={14} /> ویرایش</button>
        )}
      </div>
      <div className="ws-details-grid">
        {rows.map((row) => (
          <div key={row.label} className="ws-details-row">
            <span className="ws-details-row__label">{row.label}</span>
            <span className={`ws-details-row__value ${row.ltr ? "premium-input--ltr" : ""}`}>{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
