import { api, invalidate } from "./requestCache";

export { api };

/** Drop every cached response (used at login/logout boundaries). */
export function clearRequestCache() {
  invalidate();
}

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const ACCESS_TOKEN_KEY = "hadiflow_access_token";
const REFRESH_TOKEN_KEY = "hadiflow_refresh_token";

function clearSession() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  // Cached payloads belong to the previous session; without this a
  // different user logging in on the same browser could be served
  // another user's data from the TTL/offline cache.
  invalidate();
  window.dispatchEvent(new Event("auth-unauthorized"));
}

// یک درخواست تازه‌سازی هم‌زمان؛ اگر چند درخواست با هم 401 بگیرند،
// همگی منتظر همین یک Promise می‌مانند تا چند بار refresh نزنیم.
let refreshPromise = null;

async function refreshAccessToken() {
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refreshToken) return null;

  if (!refreshPromise) {
    // از نمونه‌ی خام axios استفاده می‌شود تا اینترسپتور دوباره فعال نشود
    refreshPromise = api
      .post(
        "/auth/refresh-token",
        { refresh_token: refreshToken },
        { skipAuthRefresh: true }
      )
      .then((res) => {
        const newToken = res.data?.access_token;
        if (newToken) localStorage.setItem(ACCESS_TOKEN_KEY, newToken);
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

    // فقط یک بار تلاش مجدد، و هرگز روی خود درخواست refresh
    if (status === 401 && !original._retried && !original.skipAuthRefresh) {
      original._retried = true;
      const newToken = await refreshAccessToken();
      if (newToken) {
        original.headers = original.headers || {};
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      }
      // تازه‌سازی شکست خورد → نشست واقعاً تمام شده است
      clearSession();
    } else if (status === 401) {
      clearSession();
    }

    return Promise.reject(error);
  }
);

// ---- Auth ----
export async function login(mobile, password) {
  // Never mix cached data across accounts on a shared browser.
  invalidate();
  const form = new URLSearchParams();
  form.append("username", mobile);
  form.append("password", password);
  const res = await api.post("/auth/login", form, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  return res.data;
}
export async function getMe() {
  const res = await api.get("/auth/me");
  return res.data;
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
