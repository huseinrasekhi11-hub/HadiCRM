import { useEffect, useState, useMemo, useCallback, memo } from "react";
import { useNavigate } from "react-router-dom";
import {
  Check, Clock, AlertCircle, Calendar, CheckCircle2,
  Phone, CalendarClock, Plus, Loader2, ChevronDown,
  Search, ArrowUpRight, X, Inbox,
} from "lucide-react";
import {
  getMyTasks, updateLeadTaskStatus, createLeadTask,
  searchLeads, setLeadFollowUp,
} from "../api/client";
import { useToast } from "../components/Toast";
import AppShell from "../components/AppShell";
import FollowUpModal from "../components/FollowUpModal";
import { statusLabel, statusColor } from "../leadStatus";
import "./Tasks.css";
import { useModalBehavior } from "../hooks/useModalBehavior";
import JalaliDatePicker from "../components/JalaliDatePicker";
import { formatTime, formatMonthDay, todayJalali } from "../utils/persian";

/* ---------- helpers (all Jalali; see utils/persian.js) ---------- */
const fmtTime = formatTime;
const fmtDay = formatMonthDay;
const jalaliTodayFull = todayJalali;

function toLocalInputValue(date) {
  if (!date) return "";
  const d = new Date(date);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function defaultDueValue() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(9, 0, 0, 0);
  return toLocalInputValue(d);
}

/* ---------- Follow-up row ---------- */
const FollowUpRow = memo(({ lead, overdue, onOpen, onReschedule }) => {
  const color = statusColor(lead.status);
  return (
    <div className={`fu-row ${overdue ? "fu-row--overdue" : ""}`}>
      <button className="fu-row__main" onClick={() => onOpen(lead.id)}>
        <span className="fu-row__bar" style={{ background: color }} />
        <span className="fu-row__body">
          <span className="fu-row__name">{lead.customer_name}</span>
          <span className="fu-row__meta">
            <span style={{ color }}>{statusLabel(lead.status)}</span>
            <span className="fu-row__dot">•</span>
            <span className="fu-row__mobile">{lead.mobile}</span>
          </span>
        </span>
        <span className={`fu-row__time ${overdue ? "fu-row__time--overdue" : ""}`}>
          <Clock size={13} />
          {lead.next_follow_up ? fmtTime(lead.next_follow_up) : "—"}
        </span>
      </button>
      <div className="fu-row__actions">
        <a className="row-action row-action--call" href={`tel:${lead.mobile}`} aria-label="تماس">
          <Phone size={16} />
        </a>
        <button className="row-action" onClick={() => onReschedule(lead)} aria-label="زمان‌بندی مجدد پیگیری">
          <CalendarClock size={16} />
        </button>
        <button className="row-action" onClick={() => onOpen(lead.id)} aria-label="باز کردن پرونده">
          <ArrowUpRight size={16} />
        </button>
      </div>
    </div>
  );
});

/* ---------- Task row ---------- */
const TaskRow = memo(({ task, onToggle, onOpenLead }) => {
  const isDone = task.status === "done";
  const isOverdue = !isDone && new Date(task.due_at).getTime() < Date.now();
  return (
    <div className={`task-row ${isDone ? "task-row--done" : ""}`}>
      <button
        className={`task-row__check ${isDone ? "task-row__check--checked" : ""} ${isOverdue ? "task-row__check--overdue" : ""}`}
        onClick={() => onToggle(task)}
        aria-label={isDone ? "بازگردانی به انجام‌نشده" : "علامت به عنوان انجام‌شده"}
      >
        {isDone && <Check size={14} strokeWidth={3} />}
      </button>
      <button className="task-row__main" onClick={() => onOpenLead(task.lead_id)}>
        <span className="task-row__body">
          <span className="task-row__title">{task.title}</span>
          {task.lead_customer_name && (
            <span className="task-row__lead">برای {task.lead_customer_name}</span>
          )}
        </span>
        <span className={`task-row__due ${isOverdue ? "task-row__due--overdue" : ""}`}>
          {isOverdue ? <AlertCircle size={13} /> : <Clock size={13} />}
          {fmtDay(task.due_at)} · {fmtTime(task.due_at)}
        </span>
      </button>
    </div>
  );
});

/* ---------- New task modal (lead picker + title + due) ---------- */
function NewTaskModal({ onClose, onSubmit }) {
  const dialogRef = useModalBehavior(onClose);
  const [search, setSearch] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [selectedLead, setSelectedLead] = useState(null);
  const [title, setTitle] = useState("");
  const [dueAt, setDueAt] = useState(defaultDueValue);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!search.trim()) { setResults([]); return; }
    const t = setTimeout(() => {
      setSearching(true);
      searchLeads({ search: search.trim(), limit: 10 })
        .then(setResults)
        .catch(() => setResults([]))
        .finally(() => setSearching(false));
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!selectedLead) { setError("یک پرونده را انتخاب کنید."); return; }
    if (!title.trim()) { setError("عنوان وظیفه را وارد کنید."); return; }
    if (!dueAt) { setError("زمان سررسید را مشخص کنید."); return; }
    setSubmitting(true);
    setError("");
    try {
      await onSubmit({
        lead_id: selectedLead.id,
        title: title.trim(),
        due_at: new Date(dueAt).toISOString(),
      });
    } catch {
      setError("ایجاد وظیفه با خطا مواجه شد.");
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal--premium" ref={dialogRef} role="dialog" aria-modal="true"
        onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <div className="modal__icon-bg"><Plus size={20} /></div>
          <div>
            <h2 className="modal__title m-0">وظیفه جدید</h2>
            <p className="modal__subtitle">وظیفه را به یک پرونده متصل کنید.</p>
          </div>
        </div>
        <form onSubmit={handleSubmit} className="modal-form mt-4">
          {/* Lead picker */}
          {!selectedLead ? (
            <div className="nt-leadpicker">
              <div className="nt-search">
                <Search size={16} className="nt-search__icon" />
                <input
                  className="premium-input premium-input--with-icon"
                  placeholder="جستجوی پرونده (نام یا موبایل)…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  autoFocus
                />
              </div>
              <div className="nt-results">
                {searching && <div className="nt-results__hint"><Loader2 size={15} className="spin" /> در حال جستجو…</div>}
                {!searching && search && results.length === 0 && (
                  <div className="nt-results__hint">پرونده‌ای یافت نشد.</div>
                )}
                {results.map((lead) => (
                  <button
                    type="button"
                    key={lead.id}
                    className="nt-result"
                    onClick={() => setSelectedLead(lead)}
                  >
                    <span className="nt-result__bar" style={{ background: statusColor(lead.status) }} />
                    <span className="nt-result__body">
                      <span className="nt-result__name">{lead.customer_name}</span>
                      <span className="nt-result__mobile">{lead.mobile}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="nt-selected">
              <span className="nt-selected__bar" style={{ background: statusColor(selectedLead.status) }} />
              <span className="nt-selected__info">
                <span className="nt-selected__name">{selectedLead.customer_name}</span>
                <span className="nt-selected__mobile">{selectedLead.mobile}</span>
              </span>
              <button type="button" className="btn-icon" onClick={() => setSelectedLead(null)} aria-label="تغییر پرونده">
                <X size={16} />
              </button>
            </div>
          )}

          <label className="field mt-3">
            <span className="field__label">عنوان وظیفه <span className="text-red-500">*</span></span>
            <input
              className="premium-input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="مثلاً: ارسال پیش‌فاکتور"
            />
          </label>
          <label className="field">
            <span className="field__label">سررسید <span className="text-red-500">*</span></span>
            <JalaliDatePicker
              withTime
              required
              value={dueAt}
              onChange={setDueAt}
            />
          </label>

          {error && <div className="form-error-banner">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>انصراف</button>
            <button type="submit" className="btn-primary" disabled={submitting || !selectedLead}>
              {submitting ? <Loader2 size={16} className="spin" /> : "ایجاد وظیفه"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ---------- Section wrapper ---------- */
function Section({ icon: Icon, title, count, tone, children }) {
  if (!count) return null;
  return (
    <section className={`dw-section dw-section--${tone}`}>
      <header className="dw-section__header">
        <Icon size={15} strokeWidth={2.5} />
        <h3 className="dw-section__title">{title}</h3>
        <span className="dw-section__count">{count}</span>
      </header>
      <div className="dw-section__list">{children}</div>
    </section>
  );
}

/* ======================================================================== */
export default function Tasks() {
  const navigate = useNavigate();
  const notify = useToast();

  const [tasks, setTasks] = useState([]);
  const [todayFollowUps, setTodayFollowUps] = useState([]);
  const [overdueFollowUps, setOverdueFollowUps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showNewTask, setShowNewTask] = useState(false);
  const [rescheduleLead, setRescheduleLead] = useState(null);
  const [completedOpen, setCompletedOpen] = useState(false);

  const loadAll = useCallback(() => {
    setLoading(true);
    setError("");
    return Promise.all([
      getMyTasks().catch(() => []),
      searchLeads({ smartFilter: "today_followup", limit: 60 }).catch(() => []),
      searchLeads({ smartFilter: "overdue", limit: 60 }).catch(() => []),
    ])
      .then(([t, tf, of]) => {
        setTasks(t);
        setTodayFollowUps(tf);
        setOverdueFollowUps(of);
      })
      .catch(() => setError("دریافت کارهای روزانه با خطا مواجه شد."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  /* ---- task grouping ---- */
  const groups = useMemo(() => {
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const tomorrowStart = todayStart + 86400000;
    const g = { overdue: [], today: [], upcoming: [], completed: [] };
    const byDue = (a, b) => new Date(a.due_at) - new Date(b.due_at);
    for (const task of tasks) {
      if (task.status === "done") { g.completed.push(task); continue; }
      if (task.status === "canceled") continue;
      const due = new Date(task.due_at).getTime();
      if (due < now.getTime()) g.overdue.push(task);
      else if (due >= todayStart && due < tomorrowStart) g.today.push(task);
      else g.upcoming.push(task);
    }
    g.overdue.sort(byDue);
    g.today.sort(byDue);
    g.upcoming.sort(byDue);
    g.completed.sort((a, b) => new Date(b.due_at) - new Date(a.due_at));
    return g;
  }, [tasks]);

  const pendingCount = groups.overdue.length + groups.today.length + groups.upcoming.length;
  const attentionCount = overdueFollowUps.length + groups.overdue.length;

  /* ---- handlers ---- */
  const handleToggleTask = useCallback(async (task) => {
    const nextStatus = task.status === "done" ? "pending" : "done";
    setTasks((prev) => prev.map((t) => (t.id === task.id ? { ...t, status: nextStatus } : t)));
    try {
      await updateLeadTaskStatus(task.lead_id, task.id, nextStatus);
      if (nextStatus === "done") notify("وظیفه انجام شد.", "success");
    } catch {
      setTasks((prev) => prev.map((t) => (t.id === task.id ? { ...t, status: task.status } : t)));
      notify("بروزرسانی وظیفه با خطا مواجه شد.", "error");
    }
  }, [notify]);

  const handleCreateTask = useCallback(async ({ lead_id, title, due_at }) => {
    const task = await createLeadTask(lead_id, { title, due_at });
    setTasks((prev) => [task, ...prev]);
    setShowNewTask(false);
    notify("وظیفه جدید ایجاد شد.", "success");
  }, [notify]);

  const handleReschedule = useCallback(async (iso) => {
    if (!rescheduleLead) return;
    try {
      await setLeadFollowUp(rescheduleLead.id, iso);
      notify("زمان پیگیری بروزرسانی شد.", "success");
      setRescheduleLead(null);
      loadAll();
    } catch {
      notify("بروزرسانی پیگیری با خطا مواجه شد.", "error");
    }
  }, [rescheduleLead, notify, loadAll]);

  const openLead = useCallback((leadId) => navigate(`/leads/${leadId}`), [navigate]);

  return (
    <AppShell>
      <div className="daily-work">
        {/* ---- Header ---- */}
        <header className="dw-header">
          <div className="dw-header__text">
            <h1 className="dw-header__title">کار روزانه</h1>
            <p className="dw-header__date">{jalaliTodayFull()}</p>
            <p className="dw-header__sub">
              {attentionCount > 0
                ? `${attentionCount} مورد عقب‌افتاده نیاز به توجه دارد`
                : pendingCount > 0
                  ? `${pendingCount} کار در انتظار انجام است`
                  : "همه‌چیز مرتب است"}
            </p>
          </div>
          <button className="btn-primary dw-header__new" onClick={() => setShowNewTask(true)}>
            <Plus size={16} strokeWidth={2.5} /> وظیفه جدید
          </button>
        </header>

        {error && <div className="alert-banner alert-banner--error">{error}</div>}

        {loading ? (
          <div className="dw-skeleton">
            <div className="skeleton" style={{ height: 80 }} />
            <div className="skeleton" style={{ height: 80 }} />
            <div className="skeleton" style={{ height: 80 }} />
          </div>
        ) : (
          <div className="dw-body">
            {/* ---- Follow-ups ---- */}
            <Section icon={AlertCircle} title="پیگیری‌های عقب‌افتاده" count={overdueFollowUps.length} tone="danger">
              {overdueFollowUps.map((lead) => (
                <FollowUpRow key={lead.id} lead={lead} overdue onOpen={openLead} onReschedule={setRescheduleLead} />
              ))}
            </Section>

            <Section icon={CalendarClock} title="پیگیری‌های امروز" count={todayFollowUps.length} tone="primary">
              {todayFollowUps.map((lead) => (
                <FollowUpRow key={lead.id} lead={lead} onOpen={openLead} onReschedule={setRescheduleLead} />
              ))}
            </Section>

            {/* ---- Tasks ---- */}
            <Section icon={AlertCircle} title="وظایف عقب‌افتاده" count={groups.overdue.length} tone="danger">
              {groups.overdue.map((task) => (
                <TaskRow key={task.id} task={task} onToggle={handleToggleTask} onOpenLead={openLead} />
              ))}
            </Section>

            <Section icon={Clock} title="وظایف امروز" count={groups.today.length} tone="primary">
              {groups.today.map((task) => (
                <TaskRow key={task.id} task={task} onToggle={handleToggleTask} onOpenLead={openLead} />
              ))}
            </Section>

            <Section icon={Calendar} title="وظایف پیش رو" count={groups.upcoming.length} tone="neutral">
              {groups.upcoming.map((task) => (
                <TaskRow key={task.id} task={task} onToggle={handleToggleTask} onOpenLead={openLead} />
              ))}
            </Section>

            {/* ---- Completed (collapsible) ---- */}
            {groups.completed.length > 0 && (
              <section className="dw-section dw-section--done">
                <button className="dw-section__toggle" onClick={() => setCompletedOpen((v) => !v)}>
                  <CheckCircle2 size={15} strokeWidth={2.5} />
                  <span className="dw-section__title">انجام‌شده</span>
                  <span className="dw-section__count">{groups.completed.length}</span>
                  <ChevronDown size={16} className={`dw-section__chevron ${completedOpen ? "dw-section__chevron--open" : ""}`} />
                </button>
                {completedOpen && (
                  <div className="dw-section__list">
                    {groups.completed.map((task) => (
                      <TaskRow key={task.id} task={task} onToggle={handleToggleTask} onOpenLead={openLead} />
                    ))}
                  </div>
                )}
              </section>
            )}

            {/* ---- Empty state ---- */}
            {pendingCount === 0 && overdueFollowUps.length === 0 && todayFollowUps.length === 0 && (
              <div className="dw-empty">
                <Inbox size={28} />
                <h3>کار باز دیگری نیست</h3>
                <p>پیگیری و وظیفه‌ی در انتظاری برای امروز وجود ندارد. می‌توانید یک وظیفه جدید بسازید.</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ---- Floating quick-add (mobile) ---- */}
      <button className="dw-fab" onClick={() => setShowNewTask(true)} aria-label="وظیفه جدید">
        <Plus size={24} strokeWidth={2.5} />
      </button>

      {/* ---- Modals ---- */}
      {showNewTask && <NewTaskModal onClose={() => setShowNewTask(false)} onSubmit={handleCreateTask} />}
      {rescheduleLead && (
        <FollowUpModal onClose={() => setRescheduleLead(null)} onSubmit={handleReschedule} />
      )}
    </AppShell>
  );
}
