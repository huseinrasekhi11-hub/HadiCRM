/**
 * Lightweight request cache for mobile / low-bandwidth conditions.
 * - In-flight dedupe: concurrent identical GETs share ONE network request
 *   (eliminates the multi-request fan-out pattern).
 * - TTL cache: reference data reused without refetch.
 * - Conditional requests: stores ETag per URL and sends If-None-Match;
 *   a 304 returns the cached body (pairs with backend ETagMiddleware).
 */
import axios from "axios";
import { getAccessToken } from "./tokenStore.js";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// `withCredentials` is what makes the browser send the HttpOnly refresh
// cookie on /auth/refresh-token and /auth/logout. Without it the session
// could never survive a page reload now that tokens are gone from
// localStorage. (On a same-origin/same-site deployment this is harmless;
// cross-site deployments additionally need SameSite=None + HTTPS.)
export const api = axios.create({ baseURL: BASE_URL, withCredentials: true });

api.interceptors.request.use((config) => {
  // The access token lives in memory only — never in localStorage.
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// NOTE: the 401 handling lives ONLY in client.js. This module used to
// register its own 401 interceptor that wiped BOTH tokens first, which
// made the refresh-token flow in client.js dead code: every expired
// access token force-logged the user out instead of silently refreshing.

const DEFAULT_TTL = 30_000;
const cache = new Map();   // key -> { data, etag, expiresAt, epoch }
const inflight = new Map(); // key -> Promise
let cacheGeneration = 0;

// Session namespace: every login/logout/session-clear boundary bumps the
// epoch, and cached entries are only served when they were stored under the
// CURRENT epoch. This guarantees a second account logging in on the same
// browser/tab can never be served the previous account's cached CRM
// payloads, even if an invalidate() call is missed or races with an
// in-flight response landing after the boundary.
let sessionEpoch = 0;

export function bumpSessionEpoch() {
  sessionEpoch += 1;
  invalidate();
}

const stableKey = (url, params) =>
  url + (params ? "?" + JSON.stringify(params, Object.keys(params).sort()) : "");

export async function cachedGet(url, { params, ttl = DEFAULT_TTL, force = false } = {}) {
  const key = stableKey(url, params);
  const entry = cache.get(key);
  const requestGeneration = cacheGeneration;
  const requestEpoch = sessionEpoch;

  if (!force && entry && entry.epoch === requestEpoch && entry.expiresAt > Date.now()) {
    return entry.data;
  }

  if (!force && inflight.has(key)) return inflight.get(key);

  const headers = {};
  if (entry?.etag) headers["If-None-Match"] = entry.etag;

  const request = api
    .get(url, { params, headers })
    .then((res) => {
      if (requestGeneration !== cacheGeneration || requestEpoch !== sessionEpoch) {
        throw new Error("Stale cached request discarded after session change.");
      }
      const next = {
        data: res.data,
        etag: res.headers.etag || entry?.etag,
        expiresAt: Date.now() + ttl,
        epoch: requestEpoch,
      };
      cache.set(key, next);
      return res.data;
    })
    .catch((err) => {
      // 304 -> serve from cache (only if it belongs to the current session)
      if (
        requestGeneration === cacheGeneration &&
        requestEpoch === sessionEpoch &&
        err.response?.status === 304 &&
        entry &&
        entry.epoch === requestEpoch
      ) {
        entry.expiresAt = Date.now() + ttl;
        return entry.data;
      }
      // Offline / network error -> serve stale cache only inside the same
      // session generation.
      if (
        requestGeneration === cacheGeneration &&
        requestEpoch === sessionEpoch &&
        !err.response &&
        entry &&
        entry.epoch === requestEpoch
      ) return entry.data;
      throw err;
    })
    .finally(() => {
      if (inflight.get(key) === request) inflight.delete(key);
    });

  inflight.set(key, request);
  return request;
}

export function invalidate(urlPrefix = "") {
  cacheGeneration += 1;
  if (!urlPrefix) {
    cache.clear();
    inflight.clear();
    return;
  }
  for (const key of cache.keys()) {
    if (key.startsWith(urlPrefix)) cache.delete(key);
  }
}

/** Call after mutations so subsequent GETs see fresh data. */
export function bustAfterMutation() {
  invalidate();
}