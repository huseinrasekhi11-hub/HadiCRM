# HadiFlow — deployment notes (security-relevant)

This document collects the settings that must be right on a real deployment.
They are the ones an audit flags most often, and most of them fail *silently*
(the app starts, then sessions or throttling misbehave).

---

## 1. Backend (Render / any host)

Start command: `bash render_start.sh`

It runs, in order: Alembic migrations → admin seed → (optional) demo data →
`uvicorn`.

### Required environment variables

| Variable | Notes |
|---|---|
| `SECRET_KEY` | ≥ 32 bytes. The app refuses to start with a short key. |
| `DATABASE_URL` | `postgresql+psycopg2://…` |
| `CORS_ORIGINS` | Comma-separated **explicit** origins of the panel. Required because requests are credentialed (`*` is not allowed with cookies). Also used as the CSRF allow-list for cookie-authenticated calls. |
| `ENABLE_SCHEDULER` | `true` on exactly **one** instance. With several workers/replicas, leave it `false` on the rest or jobs run N times. |

### Demo data is opt-in (was opt-out)

`RESEED_DEMO_DATA` defaults to **`false`**. `clear_and_reseed.py` deletes and
rebuilds the records of the four demo accounts — it must never run by accident
on a deployment that holds real data. Set `RESEED_DEMO_DATA=true` only for a
throwaway/demo instance.

### Login throttling is shared across processes

Failed-login counters live in the `login_rate_events` table, so every
worker/replica sees the same budget (`LOGIN_MAX_FAILURES_PER_ACCOUNT` per
IP+account, `LOGIN_MAX_FAILURES_PER_IP` per IP, `LOGIN_RATE_WINDOW_SECONDS`
window). A scheduled job prunes events outside the window.

* `LOGIN_RATE_BACKEND=auto` (default) — shared database + a cheap in-process
  fast path.
* `LOGIN_RATE_BACKEND=memory` — per-process only (budget × number of
  instances). Only for development, or when throttling happens at the edge
  (gateway/WAF/CDN), which is still recommended on top.

---

## 2. Frontend (Vercel / any static host)

Build variables:

| Variable | Notes |
|---|---|
| `VITE_API_BASE_URL` | Where the browser reaches the API. See the two options below. |

### Option A — same-site (recommended): proxy the API under `/api`

The browser then talks to **one** origin, so the refresh cookie is
first-party: it works in every browser (Safari and others block cross-site
cookies), no CORS preflight, no CSRF exposure.

1. Rewrite `/api/*` to the API host, e.g. in `vercel.json`:

   ```json
   {
     "rewrites": [
       { "source": "/api/:path*", "destination": "https://<api-host>/:path*" }
     ]
   }
   ```

2. Build with `VITE_API_BASE_URL=/api`.
3. On the API set `REFRESH_COOKIE_PATH=/api/auth` (the cookie path must match
   the path the *browser* uses, otherwise it is not sent at all) and
   `REFRESH_COOKIE_SAMESITE=lax`.

For local development the Vite dev server already proxies `/api` to
`http://localhost:8000` (see `frontend/vite.config.js`), so
`VITE_API_BASE_URL=/api npm run dev` gives the same first-party behaviour.

### Option B — cross-site: point straight at the API host

* `VITE_API_BASE_URL=https://api.example.com`
* API: `REFRESH_COOKIE_SAMESITE=none`, `REFRESH_COOKIE_SECURE=true`,
  `REFRESH_COOKIE_PATH=/auth`, and `CORS_ORIGINS=https://panel.example.com`.

Works in Chrome/Edge/Firefox; browsers that block third-party cookies will
sign the user out on every full page reload. Prefer option A.

---

## 3. Session model (what changed and why)

| | before | now |
|---|---|---|
| refresh token | `localStorage` (readable by any script on the page) | `HttpOnly` + `Secure` + `SameSite` cookie, scoped to the auth path |
| access token | `localStorage` | memory only (`src/api/tokenStore.js`); re-issued on reload through the refresh cookie |
| rotation | read → check → write (racy) | `SELECT … FOR UPDATE` + conditional `UPDATE … WHERE revoked_at IS NULL`; a token can be spent exactly once, even by concurrent requests |
| password change | did not exist | `POST /auth/change-password` (needs current password) and `POST /users/{id}/reset-password` for admins |

Cookie-authenticated endpoints (`/auth/refresh-token`, `/auth/logout`) are
CSRF-guarded: when the token comes from the cookie, the request's `Origin`
must be in `CORS_ORIGINS`.

---

## 4. Password recovery procedure

There is no email/SMS delivery in this project, so self-service "forgot
password" is intentionally *not* implemented. The supported flow is:

1. Admin → `POST /users/{id}/reset-password` with a temporary password
   (admin/CEO only; all of that user's sessions are revoked and the action is
   written to the audit log).
2. The admin hands the temporary password to the user through a trusted
   channel.
3. The user signs in and changes it themselves via
   `POST /auth/change-password` (or «تغییر رمز عبور» in the panel sidebar).

---

## 5. Health check

`GET /health` performs a real `SELECT 1`; it returns `503` when the database
is down, so it is safe to use as an orchestrator/uptime probe (`/` is not).

---

## 6. Known deployment caveat: the advertised URL

The repository "About" URL (`hadi-crm-flame.vercel.app`) and the URL quoted in
older audits (`hadi-crm-rho.vercel.app`) point at Vercel projects that are not
reachable from an outside network probe. This is a Vercel project setting, not
something in the repository: re-link the Vercel project (or update the About
URL in GitHub → repository settings) after deploying. Verify with:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://<panel-host>/
```
