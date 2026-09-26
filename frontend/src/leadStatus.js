import {
  StickyNote, Phone, Users as MeetingIcon, MessageSquare, MessagesSquare, Send, Mail,
  FileBox, FileText, Wrench, RefreshCw, Sparkles, UserCog, AlertTriangle, Clock,
  PlusCircle, CheckCircle2, PhoneOutgoing, Copy, Trash2, RotateCcw, Package,
} from "lucide-react";

// --- Canonical closed statuses (backend Feature 6: closed_won -> final_factor) ---
// The backend accepts "closed_won" only as a deprecated write alias; every READ
// returns "final_factor". The frontend must therefore key on "final_factor".
export const WON_STATUS = "final_factor";
export const LOST_STATUS = "closed_lost";
export const isClosedStatus = (s) => s === WON_STATUS || s === LOST_STATUS;

// --- Activity Types ---
export const ACTIVITY_TYPE_META = {
  note: { label: "یادداشت", Icon: StickyNote },
  call: { label: "تماس", Icon: Phone },
  callback: { label: "تماس مجدد", Icon: PhoneOutgoing },
  meeting: { label: "جلسه", Icon: MeetingIcon },
  message: { label: "پیام", Icon: MessageSquare },
  whatsapp: { label: "واتساپ", Icon: MessagesSquare },
  sms: { label: "پیامک", Icon: Send },
  email: { label: "ایمیل", Icon: Mail },
  catalog_sent: { label: "ارسال کاتالوگ", Icon: FileBox },
  proforma_sent: { label: "ارسال پیش‌فاکتور", Icon: FileText },
  technician_dispatched: { label: "اعزام کارشناس", Icon: Wrench },
  status_change: { label: "تغییر وضعیت", Icon: RefreshCw },
  lead_created: { label: "ایجاد لید", Icon: Sparkles },
  lead_assigned: { label: "ارجاع لید", Icon: UserCog },
  escalated: { label: "ارجاع خودکار به مدیر", Icon: AlertTriangle },
  followup_set: { label: "تنظیم پیگیری", Icon: Clock },
  task_created: { label: "ایجاد وظیفه", Icon: PlusCircle },
  task_completed: { label: "اتمام وظیفه", Icon: CheckCircle2 },
  // --- Types added by the backend evolution ---
  duplicate_detected: { label: "ثبت تکراری", Icon: Copy },
  lead_deleted: { label: "حذف پرونده", Icon: Trash2 },
  lead_restored: { label: "احیای پرونده", Icon: RotateCcw },
  sale_item_added: { label: "ثبت اقلام فروش", Icon: Package },
  other: { label: "سایر", Icon: StickyNote },
};

// --- Pipeline Stages (canonical order; final_factor replaces closed_won) ---
export const STATUS_ORDER = [
  "new",
  "contacted",
  "no_answer",
  "negotiating",
  "waiting_customer",
  "catalog_sent",
  "price_sent",
  "proforma",
  "invoice",
  "final_factor",
  "closed_lost",
];

// Stage colours run on the product's temperature axis: cool teal at first
// contact, warming through copper as the quote hardens, green once money
// lands, red when the file dies. Every token below is defined in tokens.css
// and flips for dark mode. The previous build pointed the first four stages
// at `--indigo-*`, which was never declared anywhere — so the most common
// statuses in the pipeline rendered with no colour at all, and any
// `color-mix()` that consumed them failed outright.
export const STATUS_META = {
  new:              { label: "جدید", color: "var(--stage-new)" },
  contacted:        { label: "تماس گرفته شد", color: "var(--stage-contacted)" },
  no_answer:        { label: "بی‌پاسخ", color: "var(--stage-no-answer)" },
  negotiating:      { label: "در حال مذاکره", color: "var(--stage-negotiating)" },
  waiting_customer: { label: "منتظر مشتری", color: "var(--stage-waiting)" },
  catalog_sent:     { label: "کاتالوگ ارسال شد", color: "var(--stage-catalog)" },
  price_sent:       { label: "پیش‌فاکتور قیمت ارسال شد", color: "var(--stage-price)" },
  proforma:         { label: "پروفرما", color: "var(--stage-proforma)" },
  invoice:          { label: "صدور فاکتور", color: "var(--stage-invoice)" },
  // Issuing the factor IS the successful conversion, so the closing stage is
  // named for the artefact rather than for the outcome.
  final_factor:     { label: "فاکتور", color: "var(--stage-won)" },
  closed_lost:      { label: "ناموفق", color: "var(--stage-lost)" },
};

export function statusLabel(status) {
  return STATUS_META[status]?.label || status;
}
export function statusColor(status) {
  return STATUS_META[status]?.color || "var(--text-tertiary)";
}

export const OPEN_STATUS_ORDER = STATUS_ORDER.filter((s) => !isClosedStatus(s));

// --- Task Statuses ---
export const TASK_STATUS_META = {
  pending: { label: "در انتظار", color: "var(--color-primary)" },
  done: { label: "انجام‌شده", color: "var(--color-success)" },
  canceled: { label: "لغوشده", color: "var(--text-tertiary)" },
};
export function taskStatusLabel(status) {
  return TASK_STATUS_META[status]?.label || status;
}
export function taskStatusColor(status) {
  return TASK_STATUS_META[status]?.color || "var(--text-tertiary)";
}

// --- Health Statuses ---
// Health is the same temperature axis applied to a single record: a healthy
// file is cool and green, a critical one has overheated.
export const HEALTH_META = {
  healthy:         { label: "سالم", color: "var(--health-healthy)", severity: 0.22 },
  needs_attention: { label: "نیاز به توجه", color: "var(--health-attention)", severity: 0.48 },
  at_risk:         { label: "در خطر", color: "var(--health-risk)", severity: 0.74 },
  critical:        { label: "بحرانی", color: "var(--health-critical)", severity: 1 },
};
export function healthSeverity(health) {
  return HEALTH_META[health]?.severity ?? 0;
}
export function healthLabel(health) {
  return HEALTH_META[health]?.label || "";
}
export function healthColor(health) {
  return HEALTH_META[health]?.color || "var(--text-tertiary)";
}

// --- Loss Reasons ---
export const LOSS_REASONS = [
  { value: "price", label: "قیمت" },
  { value: "competitor", label: "رقیب" },
  { value: "no_budget", label: "عدم بودجه" },
  { value: "no_need", label: "عدم نیاز" },
  { value: "no_response", label: "عدم پاسخ‌گویی مشتری" },
  { value: "wrong_customer", label: "مشتری اشتباه" },
  { value: "other", label: "سایر" },
];

// --- Action Types ---
export const ACTION_TYPES = [
  { value: "call", label: "تماس", emoji: "📞" },
  { value: "callback", label: "تماس مجدد", emoji: "🔁" },
  { value: "meeting", label: "جلسه", emoji: "🤝" },
  { value: "whatsapp", label: "واتساپ", emoji: "💬" },
  { value: "sms", label: "پیامک", emoji: "✉️" },
  { value: "email", label: "ایمیل", emoji: "📧" },
  { value: "catalog_sent", label: "ارسال کاتالوگ", emoji: "📄" },
  { value: "proforma_sent", label: "ارسال پیش‌فاکتور", emoji: "🧾" },
  { value: "technician_dispatched", label: "اعزام کارشناس", emoji: "🛠️" },
  { value: "note", label: "یادداشت", emoji: "📝" },
  { value: "other", label: "سایر", emoji: "•" },
];

export const FOLLOWUP_QUICK_OPTIONS = [
  { value: "tomorrow", label: "فردا" },
  { value: "three_days", label: "سه روز دیگر" },
  { value: "next_week", label: "هفته بعد" },
  { value: "custom", label: "انتخاب تاریخ" },
  { value: "none", label: "بدون پیگیری" },
];

export function quickFollowUpToDate(option) {
  const now = new Date();
  if (option === "tomorrow") {
    now.setDate(now.getDate() + 1);
    now.setHours(9, 0, 0, 0);
    return now;
  }
  if (option === "three_days") {
    now.setDate(now.getDate() + 3);
    now.setHours(9, 0, 0, 0);
    return now;
  }
  if (option === "next_week") {
    now.setDate(now.getDate() + 7);
    now.setHours(9, 0, 0, 0);
    return now;
  }
  return null;
}
