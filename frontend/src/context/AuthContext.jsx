import { useEffect, useMemo, useSyncExternalStore } from "react";
import { AuthContext } from "../hooks/useAuth";
import {
  bootstrapSession,
  getSnapshot,
  setAuthError,
  signIn,
  signOut,
  subscribe,
} from "./authStore";

/**
 * React binding for the session store (see `authStore.js`).
 *
 * The provider no longer owns auth state — it only subscribes to it, so a
 * login in one place (or another tab) updates every consumer in a single
 * render pass instead of through effects that run after the fact.
 */
export function AuthProvider({ children }) {
  const session = useSyncExternalStore(subscribe, getSnapshot);

  // Cold start: the access token lives in memory only, so a reload asks the
  // server for a new one using the HttpOnly refresh cookie. If there is no
  // valid cookie, this simply leaves the store "anonymous".
  useEffect(() => {
    bootstrapSession();
  }, []);

  const value = useMemo(
    () => ({
      user: session.user,
      loading: session.status === "loading",
      error: session.error,
      setError: setAuthError,
      login: signIn,
      logout: signOut,
    }),
    [session],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
