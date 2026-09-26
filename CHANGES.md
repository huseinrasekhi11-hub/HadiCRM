# Fixes applied

Every fix below was: implemented, verified against a live-running instance of
the app, checked against the full backend test suite for regressions (147
passing / 2 pre-existing failures that require real PostgreSQL and are
unrelated to this work), covered by a new regression test, and confirmed to
actually catch the original bug by temporarily reverting the fix and watching
the new test fail.

## Backend

1. **Duplicate-lead cross-user data leak** (`app/api/routes/leads.py`,
   `app/schemas/lead.py`, `frontend/src/components/NewLeadModal.jsx`)
   `POST /leads/` no longer returns another user's full lead record (name,
   need, source, owner_id) when a submitted mobile number belongs to someone
   else's lead. Returns a minimal `{status: "duplicate_attached", ...}`
   acknowledgment instead. Owners and privileged roles (admin/ceo/manager)
   still see the full record as before.
   Tests: `tests/test_duplicate_leads.py`

2. **`sale_amount` desync** (`app/crud/sale_item.py`)
   Adding a sale item to a lead after it was closed with a manually-entered
   `sale_amount` now resyncs `sale_amount` to the item total, instead of
   leaving it stuck at the old manual figure forever.
   Tests: `tests/test_product_sales_api.py`

3. **"No follow-up" didn't clear stale dates** (`app/crud/activity.py`)
   Logging a human activity with `no_followup_reason` (declining further
   follow-up) now correctly clears `lead.next_follow_up`. System-generated
   activities (status changes, etc.) are unaffected.
   Tests: `tests/test_leads_api.py`

4. **`sla_notified` never set on the "already contacted" path**
   (`app/scheduler/jobs.py`)
   The no-contact-reminder job now marks `sla_notified = True` when a rep
   contacted the lead in time, so it stops being re-evaluated on every run.
   Tests: `tests/test_scheduler_jobs.py`

5. **Escalation ignored recent reassignment** (`app/scheduler/jobs.py`)
   `escalate_stale_leads` now considers `last_assigned_at` in addition to
   `last_contact_at`/`created_at`, so a lead reassigned minutes ago is not
   immediately escalated away just because the lead itself is old.
   Tests: `tests/test_scheduler_jobs.py`

6. **`status_updated_at` timezone corruption** (`app/crud/lead.py`)
   `update_lead_status` now writes `naive_tehran_now()` instead of
   `datetime.now(timezone.utc)`, matching the column's documented contract
   and its own model default. Previously the same real moment could be
   stored ~3.5 hours apart depending on which code path wrote it, corrupting
   day-bucketing in sales-trend reports.
   Tests: `tests/test_jalali_calendar.py`

7. **Dashboard "today" used UTC midnight, not Tehran midnight**
   (`app/crud/dashboard.py`)
   `_today_bounds()` now uses the existing `jalali_today_bounds_utc()`
   helper so today's follow-ups/tasks are bucketed by the Tehran calendar
   day, consistent with the rest of the app.
   Tests: `tests/test_jalali_calendar.py`

8. **`won_this_month`/`lost_this_month` used `updated_at`**
   (`app/crud/dashboard.py`)
   Now uses `status_updated_at` with a Tehran-calendar month boundary, so
   an old won/lost lead touched by an unrelated edit is no longer
   miscounted as a fresh win/loss this month.
   Tests: `tests/test_scheduler_jobs.py`

9. **Daily digest cron had no explicit timezone** (`app/scheduler/jobs.py`)
   The 8 AM reminder job is now anchored to `Asia/Tehran` explicitly, since
   APScheduler otherwise uses the server's local timezone (UTC in most
   deployments), which fired the job at 11:30 AM Tehran time instead of
   8:00 AM. `start_scheduler()` now also returns the scheduler instance.
   Tests: `tests/test_scheduler_jobs.py`

## Frontend

10. **Notification unread-count double-polling**
    (`src/context/NotificationsContext.jsx` — new,
    `src/components/AppShell.jsx`, `src/components/NotificationBell.jsx`,
    `src/App.jsx`)
    `AppShell` and `NotificationBell` each ran their own independent
    30-second polling interval. Introduced a shared `NotificationsContext`
    that owns a single interval; both components now read/update the same
    count.

11. **`InfiniteScroll` recreated its observer on every render**
    (`src/pages/Leads.jsx`)
    `load`/`onReachEnd` are now stable via `useCallback`; the lead count
    needed for pagination offset is tracked in a ref instead of closing
    over `leads.length` directly, so the `IntersectionObserver` inside
    `InfiniteScroll` is no longer torn down and rebuilt on every keystroke.

12. **Filter/stage selection lost on page refresh** (`src/pages/Leads.jsx`)
    Selecting a smart filter or pipeline stage now writes to the URL
    (`?filter=` / `?stage=`) via `setSearchParams`, so refreshing the page
    or sharing the link restores the same filter instead of resetting to
    the default.

## Not fixed (lower-severity, flagged but out of scope for this pass)

- `needs_list`/`permissions` JSON columns use plain `default=list` instead
  of `MutableList.as_mutable(JSON)` — latent risk if a future change
  mutates these in place rather than reassigning.
- Duplicate `require_roles`/`require_admin` implementations in
  `app/auth/dependencies.py` (unused dead code; `app/permissions/permission.py`
  is what's actually used everywhere).

---

# End-to-end audit — 2026-09-26

Verified against a real PostgreSQL 16 (all 149 pre-existing tests pass;
the two "PostgreSQL-only" failures previously documented no longer occur).
Every item below was reproduced live before the fix, covered by a
regression test in `backend/tests/test_audit_regressions.py`, and the test
was confirmed to fail with the fix reverted. Final suite: 162 passed.

## Fixed

| Sev | Area | Issue |
|-----|------|-------|
| HIGH | DB / finance | `leads.sale_amount`, `sale_line_items.amount`, `lead_deletion_audits.sale_amount` were 32-bit `INTEGER`; any sale above 2,147,483,647 Rial (~2.1 billion, routine for HVAC) failed with `integer out of range`. Migration `b7c8d9e0f1a2` widens them to `BIGINT`; schemas cap at 10^15 with a clean 422. |
| HIGH | Concurrency | Concurrent `POST /leads/` with the same mobile created several independent leads (8 requests → 3 leads) instead of one lead + duplicate submissions. `create_lead` now takes a transaction-scoped `pg_advisory_xact_lock` keyed on the normalized mobile (12 concurrent → 1 lead, `duplicate_count=11`). |
| MEDIUM | Audit integrity | `POST /leads/{id}/activities` accepted system event types (`lead_deleted`, `status_change`, `escalated`, `lead_restored`, `duplicate_detected`), letting any user forge timeline/audit events. Only human action types are accepted now. |
| MEDIUM | Data integrity | Task `assigned_to_id` was never validated: unknown ids surfaced as a misleading 409, and assigning to a user who cannot see the lead produced an orphan task visible to nobody. Assignee must exist, be active, and be the lead owner or a supervisory role. |
| MEDIUM | Validation | `PATCH /leads/{id}` accepted mobiles like `12345` and blank `source`, which `POST /leads/` rejects. `LeadUpdate` now applies the same validators (returns 422; one legacy test updated from 400 accordingly). |
| MEDIUM | Admin lockout | `PUT /users/{id}` had none of the `DELETE` protections: an admin could deactivate/demote themselves or the last active admin/CEO and lock the whole admin panel. |
| MEDIUM | Frontend | Five modals/pages rendered `err.response.data.detail` directly; on any 422 that value is an array of objects and React throws ("Objects are not valid as a React child"), unmounting the modal. New `utils/apiError.js#getErrorMessage` used everywhere. |
| MEDIUM | Performance | `ETagMiddleware` read every 200 GET body into memory — including 20 MB attachment downloads — before checking `MAX_BODY`. Non-JSON and oversize responses are now passed through untouched. |
| MEDIUM | Performance | Missing indexes on `leads.owner_id` (every non-manager query), `leads.status`, `leads.created_at`, `audit_logs.created_at`, `notifications.created_at` (same migration). |
| LOW | Reliability | Scheduler rules 1 and 3 had no per-lead error isolation: one bad row aborted the whole run silently, and progress went to `print`. Each lead now runs in its own try/commit/rollback with `app_logger`. |
| LOW | Security headers | No `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Cache-Control` on any response. Added globally. |
| LOW | Data | Product names differing only in case created duplicate catalog entries. |
| LOW | Repo hygiene | `backend/uploads/` and `backend/logs/` (runtime data) were not gitignored. |

## Verified OK (no change needed)

- IDOR / horizontal access on every lead sub-resource (404 for non-owners), role gates on users/audit/deleted-leads/charts/products.
- JWT: `alg=none` rejected, refresh↔access type confusion rejected, inactive users rejected on both login and refresh, timing-equalized login.
- Path traversal on uploads, extension whitelist, 20 MB cap with cleanup on overflow.
- LIKE-wildcard escaping in lead search; no raw SQL anywhere; no `dangerouslySetInnerHTML`.
- `pip-audit` and `npm audit`: 0 known vulnerabilities. No secrets in tree or history.
- Alembic chain applies cleanly from empty DB; autogenerate diff vs models is empty (except a redundant `ix_users_id`).

## Not fixed / needs a human decision

- No login rate limiting or account lockout (needs Redis or a reverse-proxy rule).
- No password change/reset endpoint exists for anyone, including admins.
- Access tokens live in `localStorage` (XSS-exposed by design; consider httpOnly cookies).
- `status_updated_at` is naive Tehran time while everything else is UTC; `days`-window filters in charts/top-products compare it against UTC (≈3.5 h skew). Documented design debt.
- Docker image build / compose could not be exercised in this sandbox (no Docker daemon).
