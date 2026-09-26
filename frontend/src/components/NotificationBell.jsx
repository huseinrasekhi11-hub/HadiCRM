import { useEffect, useRef, useState } from "react";
import { 
  Bell, CheckCheck, Phone, Clock, Calendar, 
  ShieldAlert, UserPlus, Info, Sparkles 
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  getNotificationFeed,
  markNotificationRead,
  markAllNotificationsRead,
} from "../api/client";
import { useNotifications } from "../context/NotificationsContext";
import "./NotificationBell.css";

// Semantic mapping for enterprise look
const TYPE_META = {
  no_contact_reminder: { Icon: Clock, color: "warning", label: "یادآوری" },
  daily_followup_digest: { Icon: Calendar, color: "primary", label: "خلاصه روزانه" },
  follow_up_due: { Icon: Calendar, color: "warning", label: "سررسید پیگیری" },
  lead_escalated: { Icon: ShieldAlert, color: "danger", label: "ارجاع اضطراری" },
  lead_escalated_manager: { Icon: ShieldAlert, color: "danger", label: "ارجاع اضطراری" },
  lead_assigned: { Icon: UserPlus, color: "success", label: "ارجاع پرونده" },
  default: { Icon: Info, color: "neutral", label: "اطلاع‌رسانی" }
};

function timeAgo(iso) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "همین الان";
  if (mins < 60) return `${mins} دقیقه پیش`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} ساعت پیش`;
  const days = Math.floor(hours / 24);
  return `${days} روز پیش`;
}

export default function NotificationBell() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const { unreadCount, adjustUnreadCount, setUnreadCount, refreshUnreadCount } =
    useNotifications();
  const [feed, setFeed] = useState([]);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function toggleOpen() {
    const next = !open;
    setOpen(next);
    if (next) {
      setLoading(true);
      getNotificationFeed()
        .then((data) => {
          // Ensure chronological order (newest first)
          const sorted = data.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
          setFeed(sorted);
        })
        .finally(() => setLoading(false));
    }
  }

  async function markRead(notification, e) {
    if (e) e.stopPropagation();
    if (notification.is_read) return;
    
    // Optimistic update
    setFeed((prev) => prev.map((n) => (n.id === notification.id ? { ...n, is_read: true } : n)));
    adjustUnreadCount(-1);
    
    try {
      await markNotificationRead(notification.id);
    } catch {
      // Revert on failure
      setFeed((prev) => prev.map((n) => (n.id === notification.id ? { ...n, is_read: false } : n)));
      adjustUnreadCount(1);
    }
  }

  async function handleOpen(notification) {
    await markRead(notification);
    if (notification.lead_id) {
      setOpen(false);
      navigate(`/leads/${notification.lead_id}`);
    }
  }

  async function handleMarkAllRead() {
    // Optimistic update
    setFeed((prev) => prev.map((n) => ({ ...n, is_read: true })));
    setUnreadCount(0);
    try {
      await markAllNotificationsRead();
    } catch {
      refreshUnreadCount(); // Re-sync on failure
    }
  }

  return (
    <div className="notif-container" ref={containerRef}>
      <button 
        className={`notif-trigger ${unreadCount > 0 ? 'notif-trigger--has-unread' : ''}`} 
        onClick={toggleOpen} 
        aria-label="نوتیفیکیشن‌ها"
        aria-expanded={open}
      >
        <Bell size={18} strokeWidth={2.2} className="notif-trigger__icon" />
        {unreadCount > 0 && (
          <span className="notif-badge">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="notif-popover">
          <div className="notif-popover__header">
            <h3 className="notif-popover__title">نوتیفیکیشن‌ها</h3>
            {unreadCount > 0 && (
              <button className="notif-popover__mark-all" onClick={handleMarkAllRead}>
                <CheckCheck size={14} strokeWidth={2.5} />
                خواندن همه
              </button>
            )}
          </div>

          <div className="notif-popover__body">
            {loading ? (
              <div className="notif-loading">
                <div className="notif-skeleton" />
                <div className="notif-skeleton" />
                <div className="notif-skeleton" />
              </div>
            ) : feed.length === 0 ? (
              <div className="notif-empty">
                <div className="notif-empty__icon">
                  <Sparkles size={24} />
                </div>
                <p>شما هیچ نوتیفیکیشنی ندارید.</p>
              </div>
            ) : (
              <div className="notif-feed">
                {feed.map((n, i) => {
                  const meta = TYPE_META[n.notification_type] || TYPE_META.default;
                  const { Icon, color } = meta;
                  
                  return (
                    <div
                      key={n.id}
                      className={`notif-item ${n.is_read ? "" : "notif-item--unread"}`}
                      style={{ "--stagger": i }}
                      onClick={() => handleOpen(n)}
                    >
                      {!n.is_read && <div className="notif-item__unread-dot" />}
                      
                      <div className={`notif-item__icon-wrap notif-item__icon-wrap--${color}`}>
                        <Icon size={16} strokeWidth={2.2} />
                      </div>
                      
                      <div className="notif-item__content">
                        <div className="notif-item__title">{n.title}</div>
                        <div className="notif-item__message">{n.message}</div>
                        <div className="notif-item__time">{timeAgo(n.created_at)}</div>
                      </div>

                      {n.lead_mobile && (
                        <a
                          className="notif-item__action-btn"
                          href={`tel:${n.lead_mobile}`}
                          title={`تماس با ${n.lead_customer_name || "مشتری"}`}
                          onClick={(e) => markRead(n, e)}
                        >
                          <Phone size={14} strokeWidth={2.2} />
                        </a>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
