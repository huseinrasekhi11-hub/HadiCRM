import { createContext, useContext } from "react";

/** See the note in `useAuth.js` for why the context is not in the .jsx file. */
export const NotificationsContext = createContext(null);

export function useNotifications() {
  const ctx = useContext(NotificationsContext);
  if (!ctx) {
    throw new Error("useNotifications must be used within a NotificationsProvider");
  }
  return ctx;
}
