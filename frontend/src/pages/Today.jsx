import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Phone, RefreshCw, Sparkles, Clock, ListChecks, UserPlus,
  StickyNote, AlertTriangle,
} from "lucide-react";
import AppShell from "../components/AppShell";
import LogActionModal from "../components/LogActionModal";
import { useToast } from "../components/Toast";
import { useAuth } from "../context/AuthContext";
import {
  searchLeads, getMyTasks, createLeadActivity, updateLeadTaskStatus,
} from "../api/client";
import { statusLabel, statusColor } from "../leadStatus";
import "./Today.css";
import { todayJalali, formatTime } from "../utils/persian";

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "صبح بخیر";
  if (h < 18) return "ظهر بخیر";
  return "شب بخیر";
}

// Intl "fa-IR" renders the Persian (Jalali) calendar natively.
const jalaliToday = () =>
  todayJalali();

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

const fmtTaskTime = (iso) =>
  formatTime(iso);

/* --- One lead row: context + call + log + open. 48px targets. --- */
function LeadQueueRow({ lead, onLog, onOpen }) {
  const color = statusColor(lead.status);
  const followUp = lead.next_follow_up ? relativeFollowUp(lead.next_follow_up) : null;
  return (
    <div className="today-row" onClick={onOpen}>
      <div className="today-row__bar" style={{ background: color }} />
      <div className="today-row__body">
        <div className="today-row__title">{lead.customer_name}</div>
        <div className="today-row__meta">
          <span className="today-row__status" style={{ color }}>{statusLabel(lead.status)}</span>
          {lead.need && <span className="today-row__need">{lead.need}</span>}
          {followUp && (
            <span className={`today-row__followup ${followUp.overdue ? "today-row__followup--overdue" : ""}`}>
              <Clock size={11} /> {followUp.text}
            </span>
          )}
        </div>
      </div>
      <div className="today-row__actions" onClick={(e) => e.stopPropagation()}>
        <a className="today-action today-action--call" href={`tel:${lead.mobile}`} aria-label={`تماس با ${lead.customer_name}`}>
          <Phone size={18} />
        </a>
        <button className="today-action" onClick={() => onLog(lead)} aria-label="ثبت اقدام">
          <StickyNote size={18} />
        </button>
      </div>
    </div>
  );
}

/* --- One task row: optimistic checkbox + lead context. --- */
function TaskQueueRow({ task, onToggle, onOpen }) {
  const overdue = new Date(task.due_at).getTime() < Date.now();
  return (
    <div className="today-row">
      <button
        className="today-task-check"
        onClick={() => onToggle(task)}
        aria-label="انجام شد"
      />
      <div className="today-row__body" onClick={onOpen}>
        <div className="today-row__title">{task.title}</div>
        <div className="today-row__meta">
          {task.lead_customer_name && <span className="today-row__need">{task.lead_customer_name}</span>}
          <span className={`today-row__followup ${overdue ? "today-row__followup--overdue" : ""}`}>
            <Clock size={11} /> {fmtTaskTime(task.due_at)}
          </span>
        </div>
      </div>
    </div>
  );
}

function QueueSection({ title, tone, icon: Icon, count, children }) {
  if (!count) return null;
  return (
    <section className={`today-section today-section--${tone}`}>
      <header className="today-section__header">
        <Icon size={15} strokeWidth={2.5} />
        <h2 className="today-section__title">{title}</h2>
        <span className="today-section__count">{count}</span>
      </header>
      <div className="today-section__list">{children}</div>
    </section>
  );
}

export default function Today() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const notify = useToast();

  const [overdue, setOverdue] = useState([]);
  const [today, setToday] = useState([]);
  const [newLeads, setNewLeads] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [logLead, setLogLead] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [overdueRaw, todayRaw, newRaw, myTasks] = await Promise.all([
        searchLeads({ smartFilter: "overdue", limit: 20 }),
        searchLeads({ smartFilter: "today_followup", limit: 20 }),
        searchLeads({ smartFilter: "new", limit: 10 }),
        getMyTasks(),
      ]);
      // Backend smart filters overlap (a follow-up earlier today is both
      // "overdue" and "today") — de-duplicate so no lead appears twice.
      const overdueIds = new Set(overdueRaw.map((l) => l.id));
      setOverdue(overdueRaw);
      setToday(todayRaw.filter((l) => !overdueIds.has(l.id)));
      setNewLeads(newRaw);
      setTasks(myTasks);
    } catch {
      setError("بارگذاری کارهای امروز ناموفق بود.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const { overdueTasks, todayTasks } = useMemo(() => {
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const end = new Date(start.getTime() + 86400000);
    const pending = tasks.filter((t) => t.status === "pending");
    const byDue = (a, b) => new Date(a.due_at) - new Date(b.due_at);
    return {
      overdueTasks: pending.filter((t) => new Date(t.due_at) < now).sort(byDue),
      todayTasks: pending
        .filter((t) => {
          const d = new Date(t.due_at);
          return d >= start && d < end;
        })
        .sort(byDue),
    };
  }, [tasks]);

  const totalWork =
    overdue.length + today.length + overdueTasks.length + todayTasks.length;

  async function handleLogSubmit(payload) {
    if (!logLead) return;
    try {
      await createLeadActivity(logLead.id, payload);
      notify("اقدام ثبت شد.", "success");
      setLogLead(null);
      load(); // follow-up moved — refresh queues
    } catch {
      notify("ثبت اقدام با خطا مواجه شد.", "error");
    }
  }

  async function toggleTask(task) {
    const done = task.status === "done";
    const next = done ? "pending" : "done";
    setTasks((prev) => prev.map((t) => (t.id === task.id ? { ...t, status: next } : t)));
    try {
      await updateLeadTaskStatus(task.lead_id, task.id, next);
      if (!done) notify("وظیفه انجام شد.", "success");
    } catch {
      setTasks((prev) => prev.map((t) => (t.id === task.id ? { ...t, status: task.status } : t)));
      notify("به‌روزرسانی وظیفه با خطا مواجه شد.", "error");
    }
  }

  return (
    <AppShell>
      <div className="today-page">
        <header className="today-header">
          <div>
            <h1 className="today-header__title">
              {greeting()}، {user?.full_name}
            </h1>
            <p className="today-header__date">{jalaliToday()}</p>
          </div>
          <button className="today-refresh" onClick={load} disabled={loading} aria-label="به‌روزرسانی">
            <RefreshCw size={16} className={loading ? "spin" : ""} />
          </button>
        </header>

        {error && <div className="alert-banner alert-banner--error">{error}</div>}

        {loading ? (
          <div className="today-skeleton">
            <div className="skeleton" style={{ height: 72 }} />
            <div className="skeleton" style={{ height: 72 }} />
            <div className="skeleton" style={{ height: 72 }} />
          </div>
        ) : totalWork === 0 && newLeads.length === 0 ? (
          <div className="today-zero">
            <Sparkles size={28} />
            <h2>همه‌چیز انجام شد</h2>
            <p>پیگیری، وظیفه یا لید جدیدی در انتظار شما نیست.</p>
          </div>
        ) : (
          <div className="today-sections">
            <QueueSection title="پیگیری‌های عقب‌افتاده" tone="danger" icon={AlertTriangle} count={overdue.length}>
              {overdue.map((l) => (
                <LeadQueueRow key={l.id} lead={l} onLog={setLogLead} onOpen={() => navigate(`/leads/${l.id}`)} />
              ))}
            </QueueSection>

            <QueueSection title="پیگیری‌های امروز" tone="primary" icon={Clock} count={today.length}>
              {today.map((l) => (
                <LeadQueueRow key={l.id} lead={l} onLog={setLogLead} onOpen={() => navigate(`/leads/${l.id}`)} />
              ))}
            </QueueSection>

            <QueueSection
              title="وظایف"
              tone="warning"
              icon={ListChecks}
              count={overdueTasks.length + todayTasks.length}
            >
              {[...overdueTasks, ...todayTasks].map((t) => (
                <TaskQueueRow key={t.id} task={t} onToggle={toggleTask} onOpen={() => navigate(`/leads/${t.lead_id}`)} />
              ))}
            </QueueSection>

            <QueueSection title="لیدهای جدید — اولین تماس" tone="success" icon={UserPlus} count={newLeads.length}>
              {newLeads.map((l) => (
                <LeadQueueRow key={l.id} lead={l} onLog={setLogLead} onOpen={() => navigate(`/leads/${l.id}`)} />
              ))}
            </QueueSection>
          </div>
        )}
      </div>

      {logLead && (
        <LogActionModal onClose={() => setLogLead(null)} onSubmit={handleLogSubmit} />
      )}
    </AppShell>
  );
}
