import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useAuth } from "./AuthContext";
import { getUnreadCount } from "../api/client";

const NotificationsContext = createContext(null);

const POLL_INTERVAL_MS = 30000;

// Previously AppShell and NotificationBell each ran their own
// setInterval(getUnreadCount, 30000) independently, so every page doubled
// the polling traffic to this endpoint for the entire session. This
// provider owns the single interval; both components read/adjust the
// same shared count through useNotifications().
export function NotificationsProvider({ children }) {
  const { user } = useAuth();
  const [unreadCount, setUnreadCount] = useState(0);

  const refreshUnreadCount = useCallback(() => {
    if (!user) return;
    getUnreadCount()
      .then((d) => setUnreadCount(d.unread_count))
      .catch(() => {});
  }, [user]);

  useEffect(() => {
    if (!user) {
      setUnreadCount(0);
      return;
    }
    refreshUnreadCount();
    const interval = setInterval(refreshUnreadCount, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [user, refreshUnreadCount]);

  // Optimistic local adjustments (e.g. marking one/all notifications as
  // read) update the shared count immediately, without waiting for the
  // next poll, and without each consumer needing its own copy of it.
  const adjustUnreadCount = useCallback((delta) => {
    setUnreadCount((c) => Math.max(0, c + delta));
  }, []);

  const value = {
    unreadCount,
    setUnreadCount,
    adjustUnreadCount,
    refreshUnreadCount,
  };

  return (
    <NotificationsContext.Provider value={value}>
      {children}
    </NotificationsContext.Provider>
  );
}

export function useNotifications() {
  const ctx = useContext(NotificationsContext);
  if (!ctx) {
    throw new Error("useNotifications must be used within a NotificationsProvider");
  }
  return ctx;
}
