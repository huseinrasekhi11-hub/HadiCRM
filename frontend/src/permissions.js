/**
 * Frontend Permission Policy
 * Mirrors app/permissions/permission.py exactly.
 * Single source of truth for UI gating.
 */
export const ROLES = {
  ADMIN: "admin",
  CEO: "ceo",
  MANAGER: "manager",
  SALES_MANAGER: "sales_manager",
  SALES: "sales",
  SERVICE: "service",
  SERVICE_MANAGER: "service_manager",
  ACCOUNTING: "accounting",
  WAREHOUSE: "warehouse",
  HR: "hr",
  // نقش‌هایی که در بک‌اند (app/constants/roles.py) تعریف شده‌اند اما
  // در فرانت‌اند جا افتاده بودند؛ نبودشان باعث می‌شد برچسب کاربر
  // undefined شود و بررسی‌های دسترسی روی این نقش‌ها درست کار نکند.
  WEBSITE: "website",
  SYSTEM: "system",
  TENDER: "tender",
  POOL: "pool",
  HEAVY: "heavy",
  CUSTOMER: "customer",
};

const ALL_LEADS_ROLES = new Set([
  ROLES.ADMIN,
  ROLES.CEO,
  ROLES.MANAGER,
  ROLES.SALES_MANAGER,
]);

const ADMIN_ONLY_ROLES = new Set([
  ROLES.ADMIN,
  ROLES.CEO,
]);

export function canViewAllLeads(role) {
  return ALL_LEADS_ROLES.has(role);
}

export function canAssignAnyLead(role) {
  return ALL_LEADS_ROLES.has(role);
}

export function isAdminOnly(role) {
  return ADMIN_ONLY_ROLES.has(role);
}

export function canModifyLead(role, isOwner) {
  return canViewAllLeads(role) || isOwner;
}

export const ROLE_LABELS = {
  [ROLES.ADMIN]: "مدیر سیستم",
  [ROLES.CEO]: "مدیرعامل",
  [ROLES.MANAGER]: "مدیر",
  [ROLES.SALES_MANAGER]: "مدیر فروش",
  [ROLES.SALES]: "کارشناس فروش",
  [ROLES.SERVICE]: "خدمات پس از فروش",
  [ROLES.SERVICE_MANAGER]: "مدیر خدمات",
  [ROLES.ACCOUNTING]: "حسابداری",
  [ROLES.WAREHOUSE]: "انبار",
  [ROLES.HR]: "منابع انسانی",
  [ROLES.WEBSITE]: "وب‌سایت",
  [ROLES.SYSTEM]: "سیستم",
  [ROLES.TENDER]: "مناقصات",
  [ROLES.POOL]: "استخر",
  [ROLES.HEAVY]: "تجهیزات سنگین",
  [ROLES.CUSTOMER]: "مشتری",
};

/**
 * برچسب امن نقش: اگر نقشی ناشناخته بود، به‌جای undefined خود مقدار
 * خام برگردانده می‌شود تا رابط کاربری خالی نماند.
 */
export function roleLabel(role) {
  return ROLE_LABELS[role] || role || "—";
}
