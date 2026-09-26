import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Bell, CheckCheck, Sparkles, Clock, Calendar,
  ShieldAlert, UserPlus, Copy, Info,
} from "lucide-react";
import { getNotificationFeed, markNotificationRead, markAllNotificationsRead } from "../api/client";
import AppShell from "../components/AppShell";
import "./NotificationCenter.css";

// Semantic types from the evolved backend (Features 1 + scheduler rules)
const TYPE_META = {
  no_contact_reminder: { Icon: Clock, tone: "warning" },
  daily_followup_digest: { Icon: Calendar, tone: "primary" },
  lead_escalated: { Icon: ShieldAlert, tone: "danger" },
  lead_escalated_manager: { Icon: ShieldAlert, tone: "danger" },
  lead_assigned: { Icon: UserPlus, tone: "success" },
  duplicate_submission: { Icon: Copy, tone: "primary" },
};
const FALLBACK_META = { Icon: Info, tone: "neutral" };

function timeAgo(iso) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "همین الان";
  if (mins < 60) return `${mins} دقیقه پیش`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} ساعت پیش`;
  return `${Math.floor(hours / 24)} روز پیش`;
}

export default function NotificationCenter() {
  const navigate = useNavigate();
  const [feed, setFeed] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getNotificationFeed()
      .then((data) => setFeed(data.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function open(n) {
    if (!n.is_read) {
      setFeed((p) => p.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
      markNotificationRead(n.id).catch(() => {});
    }
    if (n.lead_id) navigate(`/leads/${n.lead_id}`);
  }

  async function markAll() {
    setFeed((p) => p.map((x) => ({ ...x, is_read: true })));
    markAllNotificationsRead().catch(() => {});
  }

  return (
    <AppShell>
      <div className="notif-center">
        <header className="notif-center__header">
          <h1 className="notif-center__title">نوتیفیکیشن‌ها</h1>
          {feed.some((n) => !n.is_read) && (
            <button className="btn-ghost" onClick={markAll}>
              <CheckCheck size={16} /> خواندن همه
            </button>
          )}
        </header>

        {loading ? (
          <div className="notif-center__skeleton">
            <div className="skeleton" style={{ height: 84 }} />
            <div className="skeleton" style={{ height: 84 }} />
            <div className="skeleton" style={{ height: 84 }} />
          </div>
        ) : feed.length === 0 ? (
          <div className="notif-center__empty">
            <Sparkles size={28} />
            <p>هیچ نوتیفیکیشنی ندارید.</p>
          </div>
        ) : (
          <ul className="notif-center__list">
            {feed.map((n) => {
              const { Icon, tone } = TYPE_META[n.notification_type] || FALLBACK_META;
              return (
                <li
                  key={n.id}
                  className={`notif-center__item ${n.is_read ? "" : "notif-center__item--unread"}`}
                  onClick={() => open(n)}
                >
                  <div className={`notif-center__item-icon notif-center__item-icon--${tone}`}>
                    <Icon size={17} strokeWidth={2.2} />
                  </div>
                  <div className="notif-center__item-body">
                    <div className="notif-center__item-title">{n.title}</div>
                    <div className="notif-center__item-msg">{n.message}</div>
                    <div className="notif-center__item-time">{timeAgo(n.created_at)}</div>
                  </div>
                  {!n.is_read && <span className="notif-center__dot" />}
                </li>
              );
            })}
          </ul>
        )}

        {/* Desktop affordance: the bell icon remains the quick entry point */}
        <div className="notif-center__hint">
          <Bell size={13} /> برای دسترسی سریع، زنگولهٔ بالای صفحه را هم دارید.
        </div>
      </div>
    </AppShell>
  );
}
