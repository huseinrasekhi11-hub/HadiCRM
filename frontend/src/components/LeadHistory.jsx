import { useEffect, useMemo, useState } from "react";
import {
  Sparkles, RefreshCw, UserCog, AlertTriangle, Phone, PhoneOutgoing, MessageSquare,
  MessagesSquare, Send, Mail, StickyNote, FileText, Paperclip, Copy, Users,
  ListChecks, CheckCircle2, Clock, Trash2, RotateCcw, Package, FileBox, Wrench,
  History, CalendarClock, Target,
} from "lucide-react";
import {
  getLeadTimeline, getLeadAttachments, getLeadDuplicateHistory,
  getAdminLeadTimeline, downloadAttachment,
} from "../api/client";
import { useAuth } from "../hooks/useAuth";
import { statusLabel, WON_STATUS, LOST_STATUS } from "../leadStatus";
import "./LeadHistory.css";

const jalaliDayFmt = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  weekday: "long", day: "numeric", month: "long", year: "numeric",
});
const jalaliDateFmt = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { dateStyle: "medium" });
const jalaliShortFmt = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { dateStyle: "short" });
const timeFmt = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { hour: "2-digit", minute: "2-digit" });

const TYPE_META = {
  lead_created: { Icon: Sparkles, cat: "milestone" },
  status_change: { Icon: RefreshCw, cat: "milestone" },
  lead_assigned: { Icon: UserCog, cat: "system" },
  escalated: { Icon: AlertTriangle, cat: "alert" },
  call: { Icon: Phone, cat: "comm" },
  callback: { Icon: PhoneOutgoing, cat: "comm" },
  meeting: { Icon: Users, cat: "comm" },
  message: { Icon: MessageSquare, cat: "comm" },
  whatsapp: { Icon: MessagesSquare, cat: "comm" },
  sms: { Icon: Send, cat: "comm" },
  email: { Icon: Mail, cat: "comm" },
  note: { Icon: StickyNote, cat: "comm" },
  catalog_sent: { Icon: FileBox, cat: "comm" },
  proforma_sent: { Icon: FileText, cat: "comm" },
  technician_dispatched: { Icon: Wrench, cat: "comm" },
  followup_set: { Icon: Clock, cat: "system" },
  task_created: { Icon: ListChecks, cat: "system" },
  task_completed: { Icon: CheckCircle2, cat: "system" },
  duplicate_detected: { Icon: Copy, cat: "dup" },
  attachment_uploaded: { Icon: Paperclip, cat: "doc" },
  lead_deleted: { Icon: Trash2, cat: "deletion" },
  lead_restored: { Icon: RotateCcw, cat: "deletion" },
  sale_item_added: { Icon: Package, cat: "resolution" },
};
const FALLBACK_META = { Icon: StickyNote, cat: "comm" };

/* Translate backend (often English) titles/descriptions into clear Persian. */
function humanize(type, title, description) {
  if (type === "lead_created") return { title: "ایجاد پرونده", description: "پرونده در سیستم ثبت شد." };
  if (type === "status_change") {
    const m = (description || "").match(/from (\w+) to (\w+)/);
    if (m) return { title: "تغییر وضعیت", description: `از «${statusLabel(m[1])}» به «${statusLabel(m[2])}»` };
    return { title: "تغییر وضعیت", description };
  }
  if (type === "lead_assigned") return { title: title || "ارجاع پرونده", description };
  return { title, description };
}

/* Turn structured metadata (Feature 3) into labeled chips. */
function metaOf(type, md) {
  const chips = [];
  md = md || {};
  if (md.assignment) {
    chips.push({ label: "از", value: md.assignment.assigned_by_name || "—" });
    chips.push({ label: "به", value: md.assignment.assigned_to_name || "—" });
    if (md.assignment.note) chips.push({ label: "یادداشت", value: md.assignment.note });
  }
  if (md.escalation) {
    if (md.escalation.reason) chips.push({ label: "دلیل", value: md.escalation.reason });
    if (md.escalation.escalated_to_name) chips.push({ label: "به", value: md.escalation.escalated_to_name });
  }
  if (md.deletion_audit) {
    chips.push({ label: "وضعیت قبلی", value: statusLabel(md.deletion_audit.previous_status) });
    if (md.deletion_audit.sale_amount)
      chips.push({ label: "مبلغ فروش", value: Number(md.deletion_audit.sale_amount).toLocaleString("fa-IR") + " ریال" });
  }
  if (md.attachment) chips.push({ label: "فایل", value: md.attachment.file_name });
  return chips;
}

function normalizeAdminEvent(ev) {
  const h = humanize(ev.event_type, ev.title, ev.description);
  return {
    key: ev.event_id,
    type: ev.event_type,
    title: h.title,
    description: h.description,
    actor: ev.actor_name,
    at: ev.occurred_at ? new Date(ev.occurred_at) : null,
    chips: metaOf(ev.event_type, ev.metadata),
  };
}

function normalizeActivity(a, currentUserId) {
  const h = humanize(a.activity_type, a.title, a.description);
  const chips = [];
  if (a.outcome) chips.push({ label: "نتیجه", value: a.outcome });
  if (a.next_follow_up) chips.push({ label: "پیگیری بعدی", value: jalaliShortFmt.format(new Date(a.next_follow_up)) });
  if (a.no_followup_reason) chips.push({ label: "بدون پیگیری", ارزش: a.no_followup_reason });
  return {
    key: `act-${a.id}`,
    type: a.activity_type,
    title: h.title,
    description: h.description,
    actor: a.user_id === currentUserId ? "شما" : "همکار",
    at: new Date(a.created_at),
    chips,
  };
}

function normalizeDuplicate(d) {
  return {
    key: `dup-${d.id}`,
    type: "duplicate_detected",
    title: `ثبت تکراری شماره ${d.submission_index}`,
    description: d.notes || `ثبت مجدد با شماره ${d.mobile}`,
    actor: d.submitted_by_full_name || "—",
    at: new Date(d.submitted_at),
    chips: [
      { label: "روش تطبیق", value: d.matched_by === "mobile_and_name" ? "موبایل و نام" : "موبایل" },
      ...(d.need ? [{ label: "نیاز", value: d.need }] : []),
    ],
  };
}

function normalizeAttachment(att, leadId) {
  return {
    key: `att-${att.id}`,
    type: "attachment_uploaded",
    title: "بارگذاری فایل",
    description: att.file_name,
    actor: null,
    at: new Date(att.created_at),
    chips: [],
    file: { leadId, id: att.id, name: att.file_name },
  };
}

const dayKey = (d) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
function dayTitle(d) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const that = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = Math.round((today - that) / 86400000);
  if (diff === 0) return "امروز";
  if (diff === 1) return "دیروز";
  return jalaliDayFmt.format(d);
}

export default function LeadHistory({ lead, refreshToken }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin" || user?.role === "ceo";
  // Everything the fetch depends on, in one key: when any part of it
  // changes the history restarts from the loading state during render
  // instead of via an effect that would render the stale history once more.
  const loadKey = `${lead.id}|${isAdmin}|${refreshToken}|${user?.id}`;
  const [state, setState] = useState(() => ({
    key: loadKey,
    events: [],
    loading: true,
    error: "",
  }));
  if (state.key !== loadKey) {
    setState({ key: loadKey, events: [], loading: true, error: "" });
  }

  useEffect(() => {
    let mounted = true;
    const load = isAdmin
      ? getAdminLeadTimeline(lead.id).then((data) => (data.events || []).map(normalizeAdminEvent))
      : Promise.all([
          getLeadTimeline(lead.id).catch(() => []),
          getLeadDuplicateHistory(lead.id).catch(() => []),
          getLeadAttachments(lead.id).catch(() => []),
        ]).then(([acts, dups, atts]) => [
          ...acts.map((a) => normalizeActivity(a, user?.id)),
          ...dups.map(normalizeDuplicate),
          ...atts.map((a) => normalizeAttachment(a, lead.id)),
        ]);
    load
      .then((evs) => {
        if (!mounted) return;
        evs.sort((a, b) => (b.at || 0) - (a.at || 0));
        setState((s) => ({ ...s, events: evs, loading: false }));
      })
      .catch(() => mounted && setState((s) => ({ ...s, error: "دریافت تاریخچه با خطا مواجه شد.", loading: false })));
    return () => { mounted = false; };
  }, [lead.id, isAdmin, refreshToken, user?.id, loadKey]);

  const { events, loading, error } = state;

  const groups = useMemo(() => {
    const map = new Map();
    for (const ev of events) {
      if (!ev.at) continue;
      const k = dayKey(ev.at);
      if (!map.has(k)) map.set(k, { date: ev.at, items: [] });
      map.get(k).items.push(ev);
    }
    return Array.from(map.values());
  }, [events]);

  const daysOpen = useMemo(
    () => Math.max(0, Math.floor((new Date().getTime() - new Date(lead.created_at).getTime()) / 86400000)),
    [lead.created_at],
  );
  const isWon = lead.status === WON_STATUS;
  const isLost = lead.status === LOST_STATUS;

  return (
    <div className="lh">
      {/* --- Lifecycle summary strip --- */}
      <div className="lh-summary">
        <div className="lh-summary__item">
          <CalendarClock size={15} />
          <span>ایجاد: {jalaliDateFmt.format(new Date(lead.created_at))}</span>
        </div>
        <div className="lh-summary__item">
          <History size={15} />
          <span>{daysOpen} روز از ایجاد</span>
        </div>
        <div className="lh-summary__item">
          <Target size={15} />
          <span>{events.length} رویداد</span>
        </div>
        {isWon && <div className="lh-summary__badge lh-summary__badge--won">فاکتور</div>}
        {isLost && <div className="lh-summary__badge lh-summary__badge--lost">ناموفق</div>}
      </div>

      {error && <div className="alert-banner alert-banner--error">{error}</div>}
      {loading && <div className="lh-loading">در حال بارگذاری تاریخچه…</div>}
      {!loading && events.length === 0 && !error && (
        <div className="lh-empty">هنوز رویدادی برای این پرونده ثبت نشده است.</div>
      )}

      {/* --- Day-grouped lifecycle timeline --- */}
      <div className="lh-timeline">
        {groups.map((g) => (
          <div className="lh-day" key={dayKey(g.date)}>
            <div className="lh-day__header">
              <span className="lh-day__title">{dayTitle(g.date)}</span>
              <span className="lh-day__count">{g.items.length} رویداد</span>
            </div>
            <div className="lh-day__events">
              {g.items.map((ev) => {
                const { Icon, cat } = TYPE_META[ev.type] || FALLBACK_META;
                return (
                  <div className={`lh-event lh-event--${cat}`} key={ev.key}>
                    <div className="lh-event__icon"><Icon size={15} /></div>
                    <div className="lh-event__body">
                      <div className="lh-event__head">
                        <span className="lh-event__title">{ev.title}</span>
                        <span className="lh-event__time">{ev.at ? timeFmt.format(ev.at) : ""}</span>
                      </div>
                      {ev.description && <div className="lh-event__desc">{ev.description}</div>}
                      {(ev.chips.length > 0 || ev.actor || ev.file) && (
                        <div className="lh-event__meta">
                          {ev.actor && <span className="lh-chip lh-chip--actor">{ev.actor}</span>}
                          {ev.chips.map((c, i) => (
                            <span className="lh-chip" key={i}><b>{c.label}:</b> {c.value}</span>
                          ))}
                          {ev.file && (
                            <a className="lh-chip lh-chip--link" href="#" rel="noreferrer"
                              onClick={(e) => { e.preventDefault(); downloadAttachment(ev.file.leadId, ev.file.id, ev.file.name).catch(() => {}); }}>
                              مشاهده فایل
                            </a>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
