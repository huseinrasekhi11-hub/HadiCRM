import { getMe, login as apiLogin, logoutSession, refreshAccessToken } from "../api/client";
import { clearRequestCache } from "../api/client";
import {
  broadcastSessionEvent,
  clearAccessToken,
  getAccessToken,
  subscribeToSessionEvents,
} from "../api/tokenStore";

/**
 * The session, as an external store.
 *
 * Auth state is not really component state: it is owned by the server (the
 * refresh session) and by the browser (the HttpOnly cookie). Keeping it in
 * `useState` inside the provider forced every update to be pushed through
 * effects — which meant an extra render right after mount and after every
 * event, and it hid the real rule: *the session is one value shared by the
 * whole app*.
 *
 * So it lives here, and `AuthProvider` reads it with `useSyncExternalStore`.
 * Nothing here touches React, which is why the async flows can update it
 * freely after an await.
 */

/** @type {{ status: "loading" | "authenticated" | "anonymous", user: object | null, error: string | null }} */
let state = { status: "loading", user: null, error: null };

const listeners = new Set();

function emit() {
  for (const listener of listeners) listener();
}

function setState(patch) {
  const next = { ...state, ...patch };
  if (
    next.status === state.status &&
    next.user === state.user &&
    next.error === state.error
  ) {
    return; // بدون تغییرِ واقعی، بدون رندرِ اضافی
  }
  state = next;
  emit();
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Identity-stable snapshot — required by useSyncExternalStore. */
export function getSnapshot() {
  return state;
}

/* ------------------------------------------------------------------ */
/* Actions                                                             */
/* ------------------------------------------------------------------ */

/**
 * Bring the store in line with the server: ask for a fresh access token
 * using the HttpOnly refresh cookie, then read the profile.
 */
export async function bootstrapSession() {
  if (!getAccessToken()) {
    await refreshAccessToken();
  }
  if (!getAccessToken()) {
    setState({ status: "anonymous", user: null, error: null });
    return null;
  }
  try {
    const me = await getMe();
    setState({ status: "authenticated", user: me, error: null });
    return me;
  } catch {
    clearAccessToken();
    setState({ status: "anonymous", user: null, error: null });
    return null;
  }
}

export async function signIn(mobile, password) {
  setState({ error: null });
  try {
    await apiLogin(mobile, password);
    const me = await getMe();
    setState({ status: "authenticated", user: me, error: null });
    broadcastSessionEvent("login");
    return me;
  } catch (err) {
    clearAccessToken();
    setState({ status: "anonymous", user: null, error: err?.message || "ورود انجام نشد." });
    throw err;
  }
}

export async function signOut() {
  await logoutSession();
  clearRequestCache();
  setState({ status: "anonymous", user: null, error: null });
  broadcastSessionEvent("logout");
}

/** The API layer saw a 401 that could not be refreshed: the session is over. */
export function endSession() {
  setState({ status: "anonymous", user: null, error: null });
}

export function setAuthError(message) {
  setState({ error: message });
}

/* ------------------------------------------------------------------ */
/* Global wiring (runs once, at module load)                           */
/* ------------------------------------------------------------------ */

// The API client announces a dead session by dispatching this event; the old
// provider listened for it inside an effect and updated state from there.
window.addEventListener("auth-unauthorized", endSession);

// Cross-tab: another tab logged in or out. No credentials live in
// localStorage any more, so the signal is a BroadcastChannel message (with a
// non-secret marker as fallback) and each tab re-reads the shared cookie.
subscribeToSessionEvents((event) => {
  if (event === "logout") {
    clearAccessToken();
    clearRequestCache();
    endSession();
  } else {
    clearAccessToken();
    clearRequestCache();
    bootstrapSession();
  }
});
