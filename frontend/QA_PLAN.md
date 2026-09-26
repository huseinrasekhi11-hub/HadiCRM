# HadiFlow — Full-Stack QA Plan

## 1. Automated suites
Run all:
```bash
alembic upgrade head
pytest tests/test_duplicate_leads.py tests/test_deleted_leads_api.py \
       tests/test_admin_lead_history.py tests/test_dashboard_charts_api.py \
       tests/test_product_sales_api.py tests/test_final_factor_status.py \
       tests/test_jalali_calendar.py tests/test_role_visibility.py \
       tests/test_integration_qa.py -v
```

## 2. Frontend — routing & auth
- [ ] `/login` → valid creds land on `/`; invalid creds show Persian error.
- [ ] Refresh any protected route while authenticated → stays (no redirect loop).
- [ ] Clear token → protected route redirects to `/login`.
- [ ] `*` unknown route → redirects to `/`.

## 3. Mobile execution (≤800px)
- [ ] Bottom nav: خانه / لیدها / ＋ / وظایف / هشدارها; unread badge updates.
- [ ] Today screen: overdue → today → tasks → new ordering; call/log/open actions work.
- [ ] FAB opens NewLeadModal; duplicate mobile shows attach toast.
- [ ] All touch targets ≥44px; no horizontal scroll.

## 4. Lead lifecycle
- [ ] Create → detail → change status through every stage.
- [ ] `closed_lost` requires reason; `closed_won` captures sale amount/products.
- [ ] Duplicate mobile (exact / +98 / Persian digits) attaches, increments count, shows in تاریخچه تکراری.
- [ ] Delete (as owner/admin) returns silently; admin sees it in حذف‌شده‌ها and can restore.
- [ ] Admin timeline shows full lifecycle incl. deletion/restoration.

## 5. Permissions
- [ ] sales sees only own leads; manager/sales_manager see all; admin/ceo see admin surfaces.
- [ ] /analytics and /deleted hidden from non-admin roles in nav and by 403.

## 6. Performance / network
- [ ] Leads list uses infinite scroll; no duplicate parallel GETs (DevTools Network).
- [ ] Second identical GET returns 304 (ETag).
- [ ] Toggle airplane mode mid-session → cached lists still render; graceful error banner on mutation.

## 7. Accessibility
- [ ] Tab through every page: visible focus ring, logical order.
- [ ] Skip link jumps to main content.
- [ ] Screen reader announces task completion / status change (LiveRegion).
- [ ] Modals trap focus and close on Escape.
- [ ] `prefers-reduced-motion` disables animations.

## 8. RTL / Persian / Jalali
- [ ] All dates render Jalali (`fa-IR-u-ca-persian`); phone numbers stay LTR.
- [ ] No layout mirroring bugs; logical properties used for new CSS.
- [ ] Persian numerals for counts/amounts (`toLocaleString("fa-IR")`).

## 9. Traceability (Part → Feature)
| Part | Delivered | Verified by |
|---|---|---|
| 0–1 | IA, routes, nav, permissions hook | Manual §2,§5 |
| 2 | Design system tokens/components | Visual review |
| 3 | Today, NotificationCenter, FAB | §3 |
| 4 | Leads workspace, pipeline, pagination | §6, auto §pagination |
| 5 | LeadDetail workspace | §4 |
| 6 | Duplicate UX | §4, auto duplicates |
| 7 | LeadHistory lifecycle | §4, auto admin history |
| 8 | Tasks cockpit | §3,§7 |
| 9 | Dashboard + analytics | auto charts |
| 10 | Role-aware UI | §5, auto role visibility |
| 11 | Jalali/RTL pass | §8, auto jalali |
| 12 | Cache, ETag, infinite scroll | §6, auto integration_qa |
| 13 | Accessibility layer | §7 |
| 14 | EmptyState/PageHeader unification | Visual consistency review |
| 15 | QA suite + plan | This document |

## 10. Final product questions (must all be YES)
1. If a salesperson had only their phone today, could they comfortably manage their work? 
2. If a manager opened the system on a large screen, could they understand business state and decide efficiently?
3. Are both experiences clearly part of the same professional product?
