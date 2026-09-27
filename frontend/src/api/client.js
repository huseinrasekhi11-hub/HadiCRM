import { api, bumpSessionEpoch } from "./requestCache";
import { setAccessToken, clearAccessToken } from "./tokenStore";

export { api };

/** Drop every cached response (used at login/logout boundaries). */
export function clearRequestCache() {
  bumpSessionEpoch();
}

/**
 * End the local side of the session.
 *
 * There are no tokens in localStorage any more: the refresh token lives in
 * an HttpOnly cookie (the server clears it) and the access token only ever
 * existed in memory. Clearing here therefore means: drop the in-memory
 * token, invalidate cached payloads and tell AuthContext to forget the user.
 */
function clearSession() {
  clearAccessToken();
  // Cached payloads belong to the previous session; bumping the epoch
  // invalidates them AND namespaces any entry still in flight, so a
  // different user logging in on the same browser can never be served
  // another user's data from the TTL/offline cache.
  bumpSessionEpoch();
  window.dispatchEvent(new Event("auth-unauthorized"));
}

// یک درخواست تازه‌سازی هم‌زمان؛ اگر چند درخواست با هم 401 بگیرند،
// همگی منتظر همین یک Promise می‌مانند تا چند بار refresh نزنیم.
let refreshPromise = null;

/**
 * Ask the server for a fresh access token.
 *
 * No body is sent: the refresh token travels in the HttpOnly cookie, which
 * script cannot read (that is the whole point). The rotated cookie comes
 * back on the response and the browser stores it for us.
 */
export async function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = api
      .post("/auth/refresh-token", {}, { skipAuthRefresh: true })
      .then((res) => {
        const newToken = res.data?.access_token;
        if (newToken) setAccessToken(newToken);
        return newToken || null;
      })
      .catch(() => null)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config || {};
    const status = error.response?.status;

    // فقط یک بار تلاش مجدد، و هرگز روی خود درخواست refresh.
    // تلاشِ ناموفقِ ورود هم ۴۰۱ است؛ آن‌جا معنای «نشست تمام شد» ندارد و
    // نیازی به refresh نیست (کوکی‌ای هم وجود ندارد).
    const isLoginCall = String(original.url || "").includes("/auth/login");
    if (status === 401 && !isLoginCall && !original._retried && !original.skipAuthRefresh) {
      original._retried = true;
      const newToken = await refreshAccessToken();
      if (newToken) {
        original.headers = original.headers || {};
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      }
      // تازه‌سازی شکست خورد → نشست واقعاً تمام شده است
      clearSession();
    } else if (status === 401 && !isLoginCall) {
      clearSession();
    }

    return Promise.reject(error);
  }
);

// ---- Auth ----
export async function login(mobile, password) {
  // Never mix cached data across accounts on a shared browser.
  bumpSessionEpoch();
  const form = new URLSearchParams();
  form.append("username", mobile);
  form.append("password", password);
  const res = await api.post("/auth/login", form, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  // The server also sets the refresh token as an HttpOnly cookie; the
  // copy in the body is only useful for non-browser clients, so it is
  // deliberately NOT persisted here.
  if (res.data?.access_token) setAccessToken(res.data.access_token);
  return res.data;
}
export async function getMe() {
  const res = await api.get("/auth/me");
  return res.data;
}
/**
 * Change the password of the logged-in account.
 *
 * The current password is required, so a stolen access token alone cannot
 * take over the account. The refresh cookie identifies the session that
 * should stay alive; every other session is revoked server-side.
 */
export async function changePassword(currentPassword, newPassword) {
  const res = await api.post("/auth/change-password", {
    current_password: currentPassword,
    new_password: newPassword,
  });
  return res.data;
}

/**
 * Server-side logout: revokes the refresh session and clears the cookie so
 * the token cannot be replayed even if it was copied before logout.
 * Best-effort — callers must clear local state regardless of the outcome.
 */
export async function logoutSession() {
  try {
    // No body: the refresh token is identified by its HttpOnly cookie.
    await api.post("/auth/logout", {}, { skipAuthRefresh: true });
  } catch {
    // network/API failure must not block local logout
  }
  clearAccessToken();
}
export async function getDashboard() {
  const res = await api.get("/dashboard/");
  return res.data;
}

// ---- Leads ----
export async function searchLeads({ search, status, smartFilter, skip = 0, limit = 100 } = {}) {
  const res = await api.get("/leads/", {
    params: {
      search: search || undefined,
      status: status || undefined,
      smart_filter: smartFilter || undefined,
      skip,
      limit,
    },
  });
  return res.data;
}
export async function searchLeadsPaged({ search, status, smartFilter, skip = 0, limit = 20 } = {}) {
  const res = await api.get("/leads/", {
    params: {
      search: search || undefined,
      status: status || undefined,
      smart_filter: smartFilter || undefined,
      skip,
      limit,
      with_total: true,
    },
  });
  const total = Number(res.headers["x-total-count"] || 0);
  return { items: res.data, total };
}
export async function getPipelineCounts({ search } = {}) {
  const res = await api.get("/leads/pipeline", { params: { search: search || undefined } });
  return res.data;
}
export async function getMyLeads() {
  const res = await api.get("/leads/my");
  return res.data;
}
export async function getLead(leadId) {
  const res = await api.get(`/leads/${leadId}`);
  return res.data;
}
export async function createLead(payload) {
  const res = await api.post("/leads/", payload);
  return res.data;
}
export async function updateLead(leadId, payload) {
  const res = await api.patch(`/leads/${leadId}`, payload);
  return res.data;
}
export async function updateLeadStatus(leadId, status, extra = {}) {
  const res = await api.patch(`/leads/${leadId}/status`, { status, ...extra });
  return res.data;
}
export async function assignLead(leadId, ownerId, note) {
  const res = await api.patch(`/leads/${leadId}/assign`, { owner_id: ownerId, note });
  return res.data;
}
export async function getLeadAssignments(leadId) {
  const res = await api.get(`/leads/${leadId}/assignments`);
  return res.data;
}
export async function getLeadEscalations(leadId) {
  const res = await api.get(`/leads/${leadId}/escalations`);
  return res.data;
}
export async function setLeadFollowUp(leadId, nextFollowUp) {
  const res = await api.patch(`/leads/${leadId}/followup`, { next_follow_up: nextFollowUp });
  return res.data;
}
export async function getLeadTimeline(leadId) {
  const res = await api.get(`/leads/${leadId}/timeline`);
  return res.data;
}
export async function getAdminLeadTimeline(leadId) {
  const res = await api.get(`/admin/leads/${leadId}/timeline`);
  return res.data;
}
export async function createLeadActivity(leadId, payload) {
  const res = await api.post(`/leads/${leadId}/activities`, payload);
  return res.data;
}

// ---- Duplicate integration (backend Feature 1) ----
export async function getLeadDuplicateHistory(leadId) {
  const res = await api.get(`/leads/${leadId}/duplicate-history`);
  return res.data;
}
export async function getLeadRelatedLeads(leadId) {
  const res = await api.get(`/leads/${leadId}/related-leads`);
  return res.data;
}

// ---- Sale items & products (backend Feature 5) ----
export async function getLeadSaleItems(leadId) {
  const res = await api.get(`/leads/${leadId}/sale-items`);
  return res.data;
}
export async function createLeadSaleItem(leadId, payload) {
  const res = await api.post(`/leads/${leadId}/sale-items`, payload);
  return res.data;
}
export async function getProducts() {
  const res = await api.get("/products/");
  return res.data;
}

// ---- Tasks ----
export async function getMyTasks() {
  const res = await api.get("/tasks/my");
  return res.data;
}
export async function getLeadTasks(leadId) {
  const res = await api.get(`/leads/${leadId}/tasks`);
  return res.data;
}
export async function createLeadTask(leadId, payload) {
  const res = await api.post(`/leads/${leadId}/tasks`, payload);
  return res.data;
}
export async function updateLeadTaskStatus(leadId, taskId, status) {
  const res = await api.patch(`/leads/${leadId}/tasks/${taskId}/status`, { status });
  return res.data;
}

// ---- Attachments ----
export async function getLeadAttachments(leadId) {
  const res = await api.get(`/leads/${leadId}/attachments`);
  return res.data;
}
export async function uploadLeadAttachment(leadId, file) {
  const form = new FormData();
  form.append("file", file);
  const res = await api.post(`/leads/${leadId}/attachments`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}
export async function deleteLead(leadId) {
  await api.delete(`/leads/${leadId}`);
}

// ---- Notifications ----
export async function getNotificationFeed(unreadOnly = false) {
  const res = await api.get("/notifications/feed", { params: { unread_only: unreadOnly } });
  return res.data;
}
export async function getUnreadCount() {
  const res = await api.get("/notifications/unread-count");
  return res.data;
}
export async function markNotificationRead(notificationId) {
  const res = await api.post(`/notifications/${notificationId}/read`);
  return res.data;
}
export async function markAllNotificationsRead() {
  const res = await api.post("/notifications/read-all");
  return res.data;
}

// ---- Users ----
export async function getUsers() {
  const res = await api.get("/users/");
  return res.data;
}
export async function getAssignableUsers() {
  const res = await api.get("/users/assignable");
  return res.data;
}

// Attachments are served ONLY through the authorized endpoint now; the
// old unauthenticated `${BASE_URL}/uploads/...` link is gone on purpose.
export async function downloadAttachment(leadId, attachmentId, fileName) {
  const res = await api.get(
    `/leads/${leadId}/attachments/${attachmentId}/download`,
    { responseType: "blob" },
  );
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName || "attachment";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

// ---- Deleted Leads (admin/CEO only) ----
export async function getDeletedLeads(params = {}) {
  const res = await api.get("/deleted-leads/", { params });
  return res.data;
}
export async function getDeletedLeadDetail(auditId) {
  const res = await api.get(`/deleted-leads/${auditId}`);
  return res.data;
}
export async function restoreDeletedLead(auditId) {
  const res = await api.post(`/deleted-leads/${auditId}/restore`);
  return res.data;
}
