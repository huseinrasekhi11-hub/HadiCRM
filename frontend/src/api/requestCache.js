/**
 * Lightweight request cache for mobile / low-bandwidth conditions.
 * - In-flight dedupe: concurrent identical GETs share ONE network request
 *   (eliminates the multi-request fan-out pattern).
 * - TTL cache: reference data reused without refetch.
 * - Conditional requests: stores ETag per URL and sends If-None-Match;
 *   a 304 returns the cached body (pairs with backend ETagMiddleware).
 */
import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const api = axios.create({ baseURL: BASE_URL });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("hadiflow_access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// NOTE: the 401 handling lives ONLY in client.js. This module used to
// register its own 401 interceptor that wiped BOTH tokens first, which
// made the refresh-token flow in client.js dead code: every expired
// access token force-logged the user out instead of silently refreshing.

const DEFAULT_TTL = 30_000;
const cache = new Map();   // key -> { data, etag, expiresAt }
const inflight = new Map(); // key -> Promise

const stableKey = (url, params) =>
  url + (params ? "?" + JSON.stringify(params, Object.keys(params).sort()) : "");

export async function cachedGet(url, { params, ttl = DEFAULT_TTL, force = false } = {}) {
  const key = stableKey(url, params);
  const entry = cache.get(key);

  if (!force && entry && entry.expiresAt > Date.now()) return entry.data;

  if (!force && inflight.has(key)) return inflight.get(key);

  const headers = {};
  if (entry?.etag) headers["If-None-Match"] = entry.etag;

  const request = api
    .get(url, { params, headers })
    .then((res) => {
      const next = {
        data: res.data,
        etag: res.headers.etag || entry?.etag,
        expiresAt: Date.now() + ttl,
      };
      cache.set(key, next);
      return res.data;
    })
    .catch((err) => {
      // 304 -> serve from cache
      if (err.response?.status === 304 && entry) {
        entry.expiresAt = Date.now() + ttl;
        return entry.data;
      }
      // Offline / network error -> serve stale cache if available
      if (!err.response && entry) return entry.data;
      throw err;
    })
    .finally(() => inflight.delete(key));

  inflight.set(key, request);
  return request;
}

export function invalidate(urlPrefix = "") {
  for (const key of cache.keys()) {
    if (!urlPrefix || key.startsWith(urlPrefix)) cache.delete(key);
  }
}

/** Call after mutations so subsequent GETs see fresh data. */
export function bustAfterMutation() {
  invalidate();
}
