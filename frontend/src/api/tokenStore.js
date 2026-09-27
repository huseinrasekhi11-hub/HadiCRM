/**
 * Where the session lives on the client — and, more importantly, where it
 * does NOT live.
 *
 * Previously both the access token and the refresh token were kept in
 * `localStorage`. Every script running on the page (including anything
 * injected through an XSS) could read them and replay the session
 * remotely, which made token theft permanent rather than opportunistic.
 *
 * Now:
 *   * refresh token  -> HttpOnly/Secure/SameSite cookie set by the server.
 *                       It is never readable or writable from JavaScript;
 *                       the browser attaches it automatically to /auth calls.
 *   * access token   -> this module, i.e. plain JavaScript memory. It is
 *                       lost on reload/tab close and is re-issued silently
 *                       through the refresh cookie (see bootstrap in
 *                       AuthContext).
 *
 * Nothing secret is persisted in `localStorage`/`sessionStorage` any more.
 * The only key we still write there is a non-secret marker used purely to
 * tell *other tabs* that the session changed (login/logout), so they can
 * re-bootstrap. It carries no token and no user data.
 */

let accessToken = null;

const listeners = new Set();

const CHANNEL_NAME = "hadiflow-auth";
const MARKER_KEY = "hadiflow_session_marker";

/** Primary cross-tab channel; absent only on very old browsers. */
const channel =
  typeof BroadcastChannel !== "undefined" ? new BroadcastChannel(CHANNEL_NAME) : null;

function notify(reason) {
  for (const listener of listeners) {
    try {
      listener(reason);
    } catch {
      /* یک شنونده‌ی خراب نباید بقیه را زمین بزند */
    }
  }
}

export function getAccessToken() {
  return accessToken;
}

export function hasAccessToken() {
  return Boolean(accessToken);
}

export function setAccessToken(token) {
  accessToken = token || null;
  notify("changed");
}

export function clearAccessToken() {
  accessToken = null;
  notify("cleared");
}

/** Subscribe to local (same tab) access-token changes. */
export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/* ------------------------------------------------------------------ */
/* Cross-tab signalling                                                */
/* ------------------------------------------------------------------ */

/**
 * Tell the other tabs that the session changed.
 * `event` is "login" or "logout".
 */
export function broadcastSessionEvent(event) {
  if (channel) {
    try {
      channel.postMessage({ type: event, at: Date.now() });
    } catch {
      /* کانال بسته شده؛ مسیرِ fallback پایین همچنان کار می‌کند */
    }
  }
  // Fallback for browsers without BroadcastChannel: the marker's mere
  // presence/removal is the signal (it holds no credentials).
  try {
    if (event === "logout") {
      localStorage.removeItem(MARKER_KEY);
    } else {
      localStorage.setItem(MARKER_KEY, String(Date.now()));
    }
  } catch {
    /* حالت ناشناس/پر بودنِ فضا: همگام‌سازیِ بین‌تبی اختیاری است */
  }
}

/**
 * Listen for session changes coming from other tabs.
 * Returns an unsubscribe function.
 */
export function subscribeToSessionEvents(handler) {
  const onMessage = (event) => {
    const type = event?.data?.type;
    if (type === "login" || type === "logout") handler(type);
  };
  if (channel) channel.addEventListener("message", onMessage);

  const onStorage = (event) => {
    if (event.key !== null && event.key !== MARKER_KEY) return;
    handler(localStorage.getItem(MARKER_KEY) ? "login" : "logout");
  };
  window.addEventListener("storage", onStorage);

  return () => {
    if (channel) channel.removeEventListener("message", onMessage);
    window.removeEventListener("storage", onStorage);
  };
}

/* ------------------------------------------------------------------ */
/* One-time migration from the localStorage-based sessions             */
/* ------------------------------------------------------------------ */
/*
 * Panels that were open (or browsers that still hold them) may carry the
 * tokens this app used to persist. Nothing reads them any more, but they are
 * long-lived credentials sitting in the one place every script on the page
 * can reach — so the first thing this module does is delete them.
 */
try {
  localStorage.removeItem("hadiflow_access_token");
  localStorage.removeItem("hadiflow_refresh_token");
} catch {
  /* حالت ناشناس یا localStorageِ غیرفعال: چیزی برای پاک‌کردن نیست */
}
