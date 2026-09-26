# HadiFlow End-to-End Audit Report

**Audit date:** 2026-09-26  
**Repository:** `hadiflow-fixed`  
**Audit posture:** code inspection + static analysis + executable regression tests + build/test attempts + migration review + security review.  
**Important constraint:** the supplied environment does not have Docker, PostgreSQL, Redis, `psql`, several declared Python runtime packages, or the frontend npm dependencies; outbound package installation also failed because DNS/network access is unavailable from the execution container. Therefore the report distinguishes verified execution from static-only conclusions.

## Executive Summary

The repository is structurally coherent: it is a FastAPI/SQLAlchemy/Alembic PostgreSQL backend, a React/Vite frontend, and a Docker Compose deployment with Postgres, a migration step, and one API service. Authentication is JWT-based with access/refresh tokens; the frontend is a protected SPA; uploaded files are intended to be private and are stored on a volume.

The audit found and fixed multiple concrete defects, including input-validation asymmetry, a destructive Alembic rollback, authenticated ETag cache-key leakage risk, incorrect Tehran/UTC analytics boundaries, task-assignment authorization, last-admin lockout, false-positive health checks, orphaned uploaded files on DB failure, missing frontend assets, insecure debug/secret defaults, inactive-account login enumeration, missing browser security headers, and a Python/Jalali dependency compatibility problem.

The application is **not fully execution-verified in this environment**. The focused environment-independent regression suite passes, but the complete backend suite cannot even be collected because the environment lacks `pwdlib`, `jdatetime`, and `psycopg2`. The frontend cannot be linted/built because `oxlint` and `vite` are not installed and `npm ci --offline` cannot hydrate the locked dependency tree. PostgreSQL-backed integration and end-to-end tests were therefore not runnable.

The most important unresolved security risks are server-side refresh-token revocation/rotation, absent login rate limiting/account lockout, and bearer/refresh tokens held in browser `localStorage`. These are confirmed architectural weaknesses from code inspection, not scanner false positives.

## Architecture / Data Flow Under Review

- **Frontend:** React 19 + React Router 7 + Vite 8. API calls use Axios. Auth state lives in `AuthContext`.
- **Backend:** FastAPI + SQLAlchemy 2 + Pydantic 2 + JWT + Argon2 via `pwdlib`.
- **Database:** PostgreSQL through `psycopg2-binary`; schema managed with Alembic.
- **Background processing:** APScheduler in the API lifespan.
- **Uploads:** local filesystem under `uploads/leads`, persisted via Docker volume in Compose.
- **Deployment:** `backend/docker-compose.yml` has `db`, `migrate`, and `api` services. The API is exposed on host port 8000 and is expected to sit behind an external TLS/reverse-proxy boundary in production.
- **Caching:** backend ETag middleware; frontend lightweight TTL/in-flight cache.
- **Authorization model:** centralized lead visibility/assignment roles plus route-level role dependencies.

## Audit Execution Log

| Area | Command / check | Result |
|---|---|---|
| Repository integrity | `git fsck --full --no-reflogs` | PASS |
| Python syntax | `python -m compileall -q backend audit_tools` | PASS |
| Focused regression tests | `pytest -q tests/test_audit_unit_regressions.py tests/test_jwt.py` | **10 passed** |
| Full backend test suite | `pytest -q` | PARTIAL / blocked during collection: 16 errors caused by unavailable project deps (`pwdlib`, `jdatetime`, `psycopg2`) |
| Frontend JS syntax | `find frontend/src -name '*.js' ... node --check` | PASS |
| Frontend lint | `npm run lint` | BLOCKED: `oxlint` not installed |
| Frontend build | `npm run build` | BLOCKED: `vite` not installed |
| NPM dependency audit | `npm audit --package-lock-only --offline` | PASS: `found 0 vulnerabilities` |
| NPM clean install | `npm ci --offline` | BLOCKED: required packages not cached (`ENOTCACHED`) |
| Python dependency install | `pip install -r backend/requirements.txt` | BLOCKED: container DNS/network unavailable |
| Python dependency audit | `pip-audit` | NOT AVAILABLE in environment |
| SAST | `ruff`, `bandit`, `semgrep` | NOT AVAILABLE in environment |
| Migration graph | `alembic history --verbose` | PASS; single head `a1b2c3d4e5f6` |
| Alembic against SQLite | `alembic upgrade head` with SQLite | NOT A VALID TARGET; fails on PostgreSQL-only SQL (`id::text`, `lpad`) |
| Alembic offline SQL | `alembic upgrade head --sql` | FAIL / tooling limitation: baseline migration calls SQLAlchemy inspection on Alembic `MockConnection` |
| Schema parity helper | `PYTHONPATH=. python audit_tools/schema_parity.py` | BLOCKED: host lacks `psycopg2` |
| Host package consistency | `python -m pip check` | FAIL in unrelated host environment (`moviepy` vs Pillow 12.3.0); not a HadiFlow dependency issue |
| Secret-file scan | tracked/config/source inspection | PASS; no tracked private key or populated `.env` found |
| Obvious frontend HTML sinks | grep for `dangerouslySetInnerHTML`, `innerHTML`, `outerHTML` | PASS; none found |
| Git whitespace | `git diff --check` | PASS |

## Bugs Found and Fixes

### 1. HIGH — Alembic baseline downgrade could destroy production CRM tables

**Location:** `backend/alembic/versions/b0c1d2e3f4a5_baseline_core_tables.py`

**Problem:** the migration is deliberately idempotent and may discover that `leads`, `tasks`, or `activities` already exist because an older deployment created them outside Alembic. Its original `downgrade()` then unconditionally dropped those tables. There is no durable marker showing whether this revision created each table.

**Impact:** `alembic downgrade` could cause catastrophic data loss.

**Fix:** `downgrade()` is now explicitly irreversible and raises a clear `RuntimeError` instructing operators to use a reviewed manual rollback/backup restore.

**Verification:** regression test added; focused suite passes 10/10.

### 2. MEDIUM — Lead mobile validation existed on create but not update

**Location:** `backend/app/schemas/lead.py:137+`

**Problem:** `LeadCreate` rejected blank/garbage mobile numbers, while `LeadUpdate` accepted them until later business logic. This produced inconsistent validation and could leave malformed lead identity data.

**Fix:** the same canonical mobile validator is applied to `LeadUpdate.mobile`.

**Verification:** Pydantic regression test rejects garbage mobile; included in 10/10 focused pass.

### 3. MEDIUM — Authenticated ETag responses did not explicitly vary by Authorization

**Location:** `backend/app/middleware/etag.py:30+`

**Problem:** user-specific GET responses were ETagged without a `Vary: Authorization` signal. In a cache/proxy capable of reusing responses incorrectly, one user’s CRM payload could be served for another bearer identity.

**Fix:** authenticated responses now add `authorization` to `Vary` while preserving existing `Vary` values.

**Verification:** regression test checks `Vary: Authorization` and 304 behavior; passed.

### 4. MEDIUM — Dashboard sales/date filters mixed UTC with naive Tehran timestamps

**Locations:** `backend/app/crud/dashboard.py`, `backend/app/api/routes/dashboard.py`

**Problem:** `Lead.status_updated_at` is a naive Tehran-local timestamp, but several analytics paths compared it with UTC-aware cutoffs. Date-only Gregorian `date_to` was also treated as an exclusive midnight boundary, excluding the requested end date.

**Fix:** analytics now use the shared Tehran-time helpers and convert public datetime inputs at the API boundary; Gregorian date-only `date_to` is made inclusive by advancing one day.

**Verification:** code-path inspection and compile checks passed. Live DB/chart verification was blocked by unavailable PostgreSQL/runtime dependencies.

### 5. MEDIUM — Structured sale items could diverge from `lead.sale_amount`

**Location:** `backend/app/crud/sale_item.py`

**Problem:** appending a sale item only updated `sale_amount` in a narrow first-item scenario. A lead could therefore have structured item totals that diverged from the headline sale amount.

**Fix:** once sale items are present, `add_sale_item()` recomputes `lead.sale_amount` from the structured items.

**Verification:** compile/static path verified; live database scenario blocked by missing PostgreSQL environment.

### 6. MEDIUM — Staff could create tasks assigned to another user

**Location:** `backend/app/api/routes/leads.py:362+`

**Problem:** the API accepted `assigned_to_id` without requiring a role capable of assigning work to other users and without verifying that the target account was active.

**Fix:** assigning to another user now requires `can_assign_any_lead(current_user)`, and the target must exist and be active.

**Verification:** code-path review; full API integration test blocked because the backend app cannot be imported in the available environment.

### 7. MEDIUM — Last active admin/CEO could be disabled or demoted

**Location:** `backend/app/api/routes/users.py:158+`

**Problem:** deleting the last active admin/CEO was guarded, but editing one could still deactivate or demote the final privileged account and lock out the management plane.

**Fix:** active admin/CEO edit requests that would deactivate or demote the last such account are rejected. The guard is limited to currently active targets to avoid false positives for already inactive accounts.

**Verification:** code review and compile check. Direct route execution was blocked by missing `pwdlib`/Postgres-backed application imports.

### 8. MEDIUM — Uploaded files could be orphaned if attachment DB persistence failed

**Location:** `backend/app/api/routes/leads.py:631+`

**Problem:** the file was written to disk before the DB row was committed. A DB error could leave an unreachable customer document on disk.

**Fix:** DB persistence is now wrapped so the just-written file is deleted if `create_attachment()` fails.

**Verification:** compile and focused regression suite pass; live failure-injection against Postgres was unavailable.

### 9. MEDIUM — Healthcheck only checked the HTTP process, not database readiness

**Locations:** `backend/app/main.py`, `backend/Dockerfile`, `backend/docker-compose.yml`

**Problem:** the old root endpoint could return `200` while PostgreSQL was unavailable, making orchestrator healthchecks report a healthy service that could not serve real requests.

**Fix:** added `/health` with `SELECT 1` and switched Docker/Compose healthchecks to it.

**Verification:** code compiles; full HTTP/DB behavior blocked by missing runtime dependencies/database.

### 10. LOW/MEDIUM — Inactive-account login response enabled account-state enumeration

**Location:** `backend/app/api/routes/auth.py:53+`

**Problem:** inactive accounts previously returned a distinguishable 403/message compared with invalid credentials.

**Fix:** inactive accounts now return the same 401 generic login failure as bad credentials, while unknown users still execute a dummy password hash verification to reduce timing differences.

**Verification:** source-level inspection; live login flow blocked by missing backend dependency stack.

### 11. HIGH — Weak default security posture in configuration

**Location:** `backend/app/config/settings.py`, `backend/.env.example`

**Problem:** development defaults previously enabled `DEBUG`, and the secret validator only warned on weak JWT signing keys.

**Fix:** `DEBUG=False` by default; `SECRET_KEY` is mandatory and must be at least 32 UTF-8 bytes. Example configuration now uses explicit placeholders and does not contain a real secret.

**Verification:** regression test checks secure default and rejects a 31-byte key; passed.

### 12. LOW — Frontend referenced missing `/logo.png`

**Locations:** `frontend/src/pages/Login.jsx`, `frontend/src/components/RequireAuth.jsx`, `frontend/src/components/AppShell.jsx`

**Problem:** repository public assets contained `favicon.svg`, not `logo.png`.

**Fix:** all affected UI references now use `/favicon.svg`.

**Verification:** static asset/reference scan finds no stale `logo.png` references. Full browser build was blocked because Vite was not installed.

### 13. MEDIUM — Basic browser security headers were missing

**Location:** `backend/app/middleware/security_headers.py`, registered in `backend/app/main.py`

**Problem:** there were no API-layer defaults for MIME sniffing, framing, or referrer leakage.

**Fix:** added `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and `Referrer-Policy: no-referrer` as low-risk hardening.

**Verification:** dedicated middleware unit test passes.

### 14. LOW — `jdatetime==5.0.0` lagged the declared Python 3.11+ support range

**Location:** `backend/requirements.txt`

**Problem:** the project declares `requires-python = ">=3.11"`, while the pinned `jdatetime` release was older than the version that explicitly added Python 3.13 support.

**Fix:** upgraded to `jdatetime==5.3.0`, which explicitly publishes Python 3.13 support, while avoiding a larger major-version jump.

**Verification:** dependency metadata was verified externally; installation could not be performed because outbound package access is unavailable. Current upstream PyPI data also shows a newer 6.1.0 release, but 5.3.0 was selected as the smaller compatibility fix.

## Security Findings — Remaining / Unresolved

### HIGH — Refresh-token replay and no server-side session revocation

**Locations:** `backend/app/api/routes/auth.py`, `backend/app/auth/jwt_handler.py`, `backend/app/models/session.py`

**Confirmed behavior:** refresh tokens contain a `jti`, but the `jti` is never persisted. `/auth/refresh-token` validates signature/type/user activity only. Logout is purely client-side. The server therefore cannot revoke a stolen refresh token before its expiry.

**Impact scenario:** a stolen refresh token can be replayed to mint new access tokens until its seven-day expiration or account deactivation.

**Recommended fix:** persist refresh-session records keyed by `jti`, rotate refresh tokens on every use, detect reuse, revoke the session on logout/disable, and expire server-side sessions independently of the JWT claim.

**Status:** NOT FIXED. This requires a schema/workflow change and could not be safely validated without the real DB.

### HIGH — No login rate limiting / brute-force control

**Location:** `backend/app/api/routes/auth.py`

**Confirmed behavior:** `/auth/login` has no rate limit, lockout, progressive delay, or shared throttling mechanism.

**Impact:** credential stuffing and password guessing remain available against the authentication surface. Argon2 hashing raises per-attempt cost but is not a substitute for request throttling.

**Recommended fix:** add distributed throttling at the API gateway/edge or a shared store, with IP + account-aware controls, backoff, and monitoring. Avoid an in-process-only limiter if multiple replicas are possible.

**Status:** NOT FIXED.

### MEDIUM — Access and refresh tokens are stored in `localStorage`

**Location:** `frontend/src/context/AuthContext.jsx`, `frontend/src/api/client.js`

**Confirmed behavior:** both tokens are written to browser `localStorage`.

**Impact:** any future same-origin XSS can exfiltrate long-lived refresh credentials. No direct unsafe HTML sink was found in the current frontend, so this is a design-level exposure rather than a demonstrated XSS exploit.

**Recommended fix:** move authentication to Secure/HttpOnly/SameSite cookies or a backend-for-frontend session architecture where practical.

**Status:** NOT FIXED.

### MEDIUM — Duplicate-lead creation has a check-then-insert race

**Location:** `backend/app/crud/lead.py:148+`; `mobile_normalized` is indexed but not unique.

**Confirmed behavior:** two concurrent requests can both see no existing normalized mobile and insert separate leads before either sees the other row.

**Impact:** duplicate ownership, duplicate CRM records, and inconsistent analytics under concurrent submissions.

**Recommended fix:** use a database-level concurrency primitive appropriate to the business rule (for example, an advisory lock/serializable section or a carefully designed unique-key strategy that preserves the intended “duplicate submission” semantics).

**Status:** NOT FIXED.

### MEDIUM — Scheduler is not safe for multiple workers/replicas

**Location:** `backend/app/main.py` lifespan and `backend/app/scheduler/jobs.py`

**Confirmed behavior:** APScheduler starts inside each API process when `ENABLE_SCHEDULER=true`. The code comments acknowledge this.

**Impact:** running multiple Uvicorn workers or multiple containers can execute reminders/escalations more than once and create duplicate notifications/assignments.

**Recommended fix:** run one dedicated scheduler worker or introduce a distributed job lock/leader-election mechanism.

**Status:** NOT FIXED.

### MEDIUM — Audit-log writes fail open and silently

**Location:** `backend/app/crud/audit_log.py`

**Confirmed behavior:** `create_audit_log()` catches every exception, rolls back, prints, and returns `None`.

**Impact:** a business mutation can commit successfully while its security/compliance audit record disappears without failing the operation or creating an alert.

**Recommended fix:** use transactional coupling/outbox/event logging, or make audit durability a monitored failure condition. Replace raw `print` with structured logging even if a non-fatal policy is retained.

**Status:** NOT FIXED.

### MEDIUM — User mobile identity is not normalized consistently

**Location:** `backend/app/schemas/user.py`, `backend/app/crud/user.py`, `backend/app/core/text_normalization.py`

**Confirmed behavior:** user mobile input accepts normalized Persian/Arabic digit and country-code variants, but the raw submitted value is stored and login queries exact raw `User.mobile` equality.

**Impact:** equivalent phone numbers can be stored as distinct user identities, and a user may fail to log in if they later enter an equivalent representation.

**Recommended fix:** store a canonical mobile field for identity/uniqueness and use that canonical key for authentication. Migrate existing data carefully before adding a unique constraint.

**Status:** NOT FIXED.

### MEDIUM — Production TLS / reverse-proxy boundary is outside the repository

**Location:** `backend/docker-compose.yml`

**Confirmed behavior:** API port 8000 is directly published by Compose; the repository contains no TLS reverse proxy configuration.

**Impact:** deploying this Compose file directly to the public internet would expose an HTTP API without transport encryption.

**Recommended fix:** document and enforce the expected ingress model, preferably terminating TLS at a managed reverse proxy/load balancer and restricting the backend bind surface accordingly.

**Status:** NOT FIXED / deployment-environment dependent.

### MEDIUM — No CI workflow is present in the repository

**Location:** `.github/workflows/` absent.

**Impact:** there is no repository-enforced clean install, full test, migration, lint, or security gate before deployment.

**Recommended fix:** add CI that installs backend/frontend dependencies, runs the full suite against PostgreSQL, runs lint/type/security checks, builds the frontend, and validates migrations.

**Status:** NOT FIXED.

### LOW/INFO — Alembic offline SQL generation is unsupported

**Location:** `backend/alembic/versions/b0c1d2e3f4a5_baseline_core_tables.py`

**Confirmed behavior:** the compatibility baseline uses `sa.inspect(op.get_bind())`; Alembic's offline `MockConnection` cannot be inspected.

**Impact:** `alembic upgrade head --sql` cannot generate offline SQL.

**Recommended fix:** split dialect-independent offline SQL from online introspection or explicitly document that this chain requires an online database connection.

**Status:** NOT FIXED.

## Security Non-Findings / Defenses Confirmed

- No `dangerouslySetInnerHTML`, `innerHTML`, `outerHTML`, `eval`, `pickle`, `yaml.load`, shell execution, or obvious command-injection sinks were found in the application source scan.
- Attachment downloads are no longer publicly mounted under `/uploads`; the code checks the lead's authorization, matches attachment-to-lead IDs, and verifies real-path containment.
- Attachment filenames are reduced to safe basenames, constrained by an extension allow-list, and stored using UUID-based server-side names.
- The frontend external WhatsApp link uses `target="_blank"` with `rel="noreferrer"`.
- Backend route checks are not relying on frontend-only authorization: lead visibility/assignment and admin endpoints have server-side dependencies.
- Default CORS origins are explicit, not wildcarded; credentials are enabled only for those configured origins.
- No populated `.env`, PEM/private-key, or obvious secret file was found in the audited source tree. The scan did find the virtual-environment CA bundle; that is not a project secret.

## Dependency Review

### Frontend

The locked Axios version is **1.20.0**, and `npm audit --package-lock-only --offline` reported **0 vulnerabilities**. Upstream Axios security advisories published September 16, 2026 are addressed in the maintained release line; no confirmed lockfile vulnerability was identified from the current advisory set.

### Backend

A Python vulnerability scanner could not run because `pip-audit` is not installed and package installation is blocked by network/DNS restrictions. Manual advisory review did not identify a confirmed vulnerability in the pinned PyJWT 2.14.0, pydantic-settings 2.7.0, python-multipart 0.0.32, or APScheduler 3.11.0 versions. PyJWT 2.15.0 is newer, but 2.13.0 already contained the relevant security-release wave, so 2.14.0 was not treated as vulnerable merely for being behind latest.

`jdatetime` was upgraded from 5.0.0 to 5.3.0 to align explicit Python 3.13 support with the project's Python >=3.11 declaration.

No dependency conclusion above should be read as a substitute for a clean online `pip-audit` run in CI.

## Configuration / Deployment Findings

- `DEBUG=False` is now the default.
- `SECRET_KEY` is required and has a minimum length of 32 bytes.
- `.env.example` uses placeholders rather than credentials.
- Docker runs the backend as non-root `appuser`.
- Uploads and PostgreSQL data are backed by named volumes.
- Database service health is a Compose dependency of migration and API startup.
- Database port 5432 is no longer exposed to the host by Compose.
- The API healthcheck is now DB-aware.
- Scheduler duplication risk remains for multi-worker/multi-replica production deployments.
- Direct host publication of port 8000 still assumes an external TLS/reverse-proxy layer for production.

## Frontend Findings

- Protected routes are wrapped by `RequireAuth`.
- Frontend route gating is not treated as the security boundary; backend authorization remains responsible.
- No obvious unsafe HTML injection sink was found.
- Axios request interception refreshes access tokens once and synchronizes concurrent refresh attempts through a shared promise.
- Frontend cache data is now namespaced by a browser session identifier and synchronized across tabs to reduce cross-account cache mixing.
- No real browser E2E was possible because Vite/oxlint/npm install could not be executed in the offline environment.

## Database Findings

**Confirmed:** Alembic has one linear head, and the baseline migration was specifically introduced to repair a historical mismatch between migration history and `Base.metadata.create_all` deployment state.

**Unverified:** fresh PostgreSQL installation, upgrade from every historical revision, data-preserving rollback sequence, concurrent duplicate lead creation, query plans/index effectiveness, and real transaction/deadlock behavior. These require a live PostgreSQL service.

**Known tooling limitation:** the baseline migration cannot generate offline SQL because it performs online schema introspection.

## Performance / Reliability Review

Positive findings:

- Lead lists have explicit pagination limits.
- Search escapes SQL `LIKE` wildcards.
- Frontend request cache supports in-flight deduplication and TTL reuse.
- ETag middleware avoids retransmitting small unchanged JSON responses.
- Uploads are streamed in 1 MiB chunks with a 20 MiB limit.
- Structured sale totals are aggregated in SQL rather than by loading every row into Python.

Remaining concerns:

- Duplicate lead creation is still race-prone under concurrency.
- Scheduler side effects can duplicate across replicas.
- Audit-log persistence is non-durable on error.
- `get_notifications()` counts a user's leads without excluding soft-deleted leads, which can make the summary count stale.
- No load test or query-plan analysis was possible without a live PostgreSQL environment.

## Changes Made

1. Added `LeadUpdate.mobile` validation.
2. Fixed user-field Alembic downgrade to preserve parent columns.
3. Made the compatibility baseline migration explicitly irreversible rather than destructive.
4. Added authenticated `Vary: Authorization` handling to ETag responses.
5. Corrected Tehran-local/UTC dashboard analytics and inclusive Gregorian `date_to` handling.
6. Synchronized structured sale items to `lead.sale_amount` when appending items.
7. Enforced task assignee authorization and active-user checks.
8. Protected the last active admin/CEO from deactivation/demotion.
9. Added orphan-file cleanup if attachment DB persistence fails.
10. Added DB-aware `/health` and updated container healthchecks.
11. Hardened login error uniformity for inactive accounts.
12. Hardened default settings (`DEBUG=False`, minimum `SECRET_KEY`).
13. Added browser security headers middleware.
14. Replaced missing `/logo.png` references with `/favicon.svg`.
15. Added session-namespaced frontend cache plus cross-tab auth synchronization.
16. Normalized `frontend/vercel.json` line endings/whitespace.
17. Upgraded `jdatetime` from 5.0.0 to 5.3.0.
18. Added environment-independent regression tests covering the major fixes.

The supplied archive already contained pre-existing uncommitted changes in at least `frontend/src/pages/Home.jsx` and `frontend/vercel.json`; these were treated as part of the supplied baseline rather than discarded.

## Remaining Problems / Blockers

1. Full backend test execution is blocked by missing `pwdlib`, `jdatetime`, and `psycopg2` in the audit environment.
2. Frontend build/lint is blocked by missing `vite` and `oxlint`; offline `npm ci` cannot hydrate the lockfile.
3. PostgreSQL integration/E2E verification was impossible because no Postgres server or `psql` client is available.
4. Docker-based deployment verification was impossible because Docker is not installed.
5. Python package vulnerability scanning was incomplete because `pip-audit` is unavailable and external package installation is blocked.
6. Browser-level mobile/responsive testing was not possible.

## Running Audit Checklist

| Major area | Status | Notes |
|---|---|---|
| Project structure | ✅ PASS | Architecture and execution paths inspected. |
| Build — backend syntax | ✅ PASS | `compileall` clean. |
| Build — frontend | ⚠️ PARTIAL | Vite unavailable in environment. |
| Unit/regression tests | ✅ PASS | Focused 10/10 pass. |
| Complete backend suite | ⚠️ PARTIAL | 16 collection errors caused by unavailable dependencies. |
| Frontend lint | ⚠️ PARTIAL | `oxlint` unavailable. |
| Frontend build | ⚠️ PARTIAL | `vite` unavailable. |
| APIs | ⚠️ PARTIAL | Static endpoint/authorization inspection; live API tests blocked. |
| Database | ⚠️ PARTIAL | Migration graph verified; live Postgres unavailable. |
| Authentication | ⚠️ PARTIAL | JWT/unit logic verified; live login/refresh flow not executable. |
| Authorization | ⚠️ PARTIAL | Server-side policies inspected and one concrete task-assignment issue fixed; live RBAC matrix blocked. |
| Security | ⚠️ PARTIAL | Static/manual security review plus regression tests; dynamic scanning limited by tools/environment. |
| Dependencies | ⚠️ PARTIAL | NPM audit clean; Python scanner unavailable; manual advisory review performed. |
| Configuration | ✅ PASS | Secure defaults and Compose configuration inspected. |
| Infrastructure/deployment | ⚠️ PARTIAL | Docker/Compose reviewed but not executed. |
| Performance | ⚠️ PARTIAL | Static review only; no live DB/query/load measurements. |
| Error handling/observability | ⚠️ PARTIAL | Central DB errors/health audited; audit-log durability remains an issue. |
| Repository integrity | ✅ PASS | `git fsck` and whitespace checks clean. |

## Final Status

**Audit conclusion:** the codebase has meaningful, verified fixes and no confirmed critical remote-compromise issue was found during the available static/manual review. However, it is **not fully proven production-ready in this environment** because the complete backend suite, frontend build, PostgreSQL migrations, API E2E, and Docker deployment could not be executed.

The highest-priority engineering work remaining is to implement refresh-token revocation/rotation and login throttling, then run the entire test/security/deployment suite in a real Postgres + dependency-complete CI environment.
