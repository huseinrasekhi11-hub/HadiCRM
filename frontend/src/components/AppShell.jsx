import { useState, useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutGrid, Users, ListChecks, LogOut, Bell,
  ChevronLeft, ChevronRight, BarChart3, Trash2, MoreHorizontal, X,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useNotifications } from "../context/NotificationsContext";
import { usePermissions } from "../hooks/usePermissions";
import NotificationBell from "./NotificationBell";
import ThemeToggle from "./ThemeToggle";
import QuickActionFab from "./QuickActionFab";
import LiveRegion from "./LiveRegion";
import "./AppShell.css";

function buildDesktopNav(isAdmin) {
  const items = [
    { to: "/", end: true, label: "داشبورد", Icon: LayoutGrid },
    { to: "/leads", end: false, label: "لیدها", Icon: Users },
    { to: "/tasks", end: false, label: "وظایف", Icon: ListChecks },
  ];
  if (isAdmin) {
    items.push({ to: "/analytics", end: false, label: "تحلیل‌ها", Icon: BarChart3 });
    items.push({ to: "/deleted", end: false, label: "حذف‌شده‌ها", Icon: Trash2 });
  }
  return items;
}

// Routes that are not in the rail still deserve a correct breadcrumb rather
// than the generic fallback the previous version showed.
const EXTRA_CRUMBS = [
  { match: (p) => p.startsWith("/leads/"), label: "پروندهٔ مشتری" },
  { match: (p) => p.startsWith("/notifications"), label: "اعلان‌ها" },
  { match: (p) => p.startsWith("/analytics"), label: "تحلیل‌ها" },
  { match: (p) => p.startsWith("/deleted"), label: "حذف‌شده‌ها" },
];

/*
 * Admin-only destinations that have no room in the five-slot bottom bar.
 * On desktop they live in the sidebar rail; on mobile they are reachable
 * from the «بیشتر» sheet in the header, so nothing is lost without the rail.
 */
const MOBILE_MORE_LINKS = [
  { to: "/analytics", label: "تحلیل‌ها", Icon: BarChart3 },
  { to: "/deleted", label: "حذف‌شده‌ها", Icon: Trash2 },
];

function initials(name) {
  if (!name) return "؟";
  return name.trim().split(/\s+/).slice(0, 2).map((p) => p[0]).join("");
}

// Persian digits for counts shown in badges, so a "3" never appears in Latin
// numerals beside Persian text.
const faNum = (n) => Number(n).toLocaleString("fa-IR");

export default function AppShell({ children }) {
  const { user, logout } = useAuth();
  const { isAdmin, roleLabel } = usePermissions();
  const location = useLocation();

  const [isCollapsed, setIsCollapsed] = useState(
    () => localStorage.getItem("hadiflow_sidebar_collapsed") === "true"
  );
  /* The mobile «بیشتر» sheet (admin-only destinations). */
  const [moreOpen, setMoreOpen] = useState(false);
  const { unreadCount: unread } = useNotifications();
  const navItems = buildDesktopNav(isAdmin);

  /* Close the sheet whenever the route changes — tapping a link should land
   * on the page with the menu out of the way. */
  useEffect(() => { setMoreOpen(false); }, [location.pathname]);

  useEffect(() => {
    if (!moreOpen) return;
    const onKey = (e) => { if (e.key === "Escape") setMoreOpen(false); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [moreOpen]);

  useEffect(() => {
    localStorage.setItem("hadiflow_sidebar_collapsed", isCollapsed);
    document.documentElement.style.setProperty(
      "--sidebar-width",
      isCollapsed ? "68px" : "244px"
    );
  }, [isCollapsed]);

  const toggleSidebar = () => setIsCollapsed((v) => !v);

  const currentCrumb =
    navItems.find((item) =>
      item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to)
    )?.label ||
    EXTRA_CRUMBS.find((c) => c.match(location.pathname))?.label ||
    "جزئیات";

  return (
    <div className={`app-layout ${isCollapsed ? "app-layout--collapsed" : ""}`}>
      <a href="#main-content" className="skip-link">پرش به محتوای اصلی</a>

      {/* --- Desktop rail --- */}
      <aside className="sidebar" aria-label="ناوبری اصلی">
        <div className="sidebar__header">
          <a href="/" className="sidebar__brand" aria-label="HadiFlow">
            <img src="/logo.png" alt="" className="sidebar__logo" />
            {!isCollapsed && <span className="sidebar__brand-name">HadiFlow</span>}
          </a>
          {!isCollapsed && (
            <button
              className="sidebar__collapse-btn"
              onClick={toggleSidebar}
              aria-label="بستن منو"
              aria-expanded="true"
            >
              <ChevronRight size={16} />
            </button>
          )}
        </div>

        {isCollapsed && (
          <button
            className="sidebar__collapse-btn"
            onClick={toggleSidebar}
            aria-label="باز کردن منو"
            aria-expanded="false"
            style={{ margin: "8px auto 0" }}
          >
            <ChevronLeft size={16} />
          </button>
        )}

        <nav className="sidebar__nav">
          {navItems.map(({ to, end, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `nav-item ${isActive ? "nav-item--active" : ""}`}
              title={isCollapsed ? label : undefined}
            >
              <div className="nav-item__icon-wrapper"><Icon size={18} strokeWidth={2} /></div>
              {!isCollapsed && <span className="nav-item__label">{label}</span>}
              <div className="nav-item__indicator" />
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__footer">
          {!isCollapsed && (
            <div className="sidebar__user-profile">
              <div className="sidebar__avatar" aria-hidden="true">{initials(user?.full_name)}</div>
              <div className="sidebar__user-info">
                <div className="sidebar__user-name">{user?.full_name}</div>
                <div className="sidebar__user-role">{roleLabel}</div>
              </div>
            </div>
          )}
          <div className="sidebar__actions">
            {isCollapsed && (
              <div className="sidebar__avatar sidebar__avatar--mini" title={user?.full_name}>
                {initials(user?.full_name)}
              </div>
            )}
            <button className="sidebar__action-btn" onClick={logout} title="خروج از حساب">
              <LogOut size={16} strokeWidth={2} />
              {!isCollapsed && <span>خروج از حساب</span>}
            </button>
          </div>
        </div>
      </aside>

      {/* --- Mobile header --- */}
      <header className="mobile-header">
        <a href="/" className="mobile-header__brand" aria-label="HadiFlow">
          <img src="/logo.png" alt="" className="mobile-header__logo" />
        </a>
        <div className="mobile-header__actions">
          {isAdmin && (
            <button
              className={`mobile-more-btn ${moreOpen ? "mobile-more-btn--open" : ""}`}
              onClick={() => setMoreOpen((v) => !v)}
              aria-label="سایر بخش‌ها"
              aria-expanded={moreOpen}
              aria-controls="mobile-more-sheet"
            >
              <MoreHorizontal size={18} strokeWidth={2} />
            </button>
          )}
          <ThemeToggle />
          <button className="mobile-logout-btn" onClick={logout} aria-label="خروج از حساب">
            <LogOut size={18} strokeWidth={2} />
          </button>
        </div>
      </header>

      {/* --- Mobile «بیشتر» sheet: the admin pages that have no slot in the
          bottom bar (the desktop rail is hidden below 800px). --- */}
      {isAdmin && moreOpen && (
        <>
          <div className="mobile-more-backdrop" onClick={() => setMoreOpen(false)} aria-hidden="true" />
          <div className="mobile-more-sheet" id="mobile-more-sheet" role="menu" aria-label="سایر بخش‌ها">
            <div className="mobile-more-sheet__head">
              <span>بخش‌های مدیریتی</span>
              <button className="mobile-more-sheet__close" onClick={() => setMoreOpen(false)} aria-label="بستن منو">
                <X size={16} strokeWidth={2} />
              </button>
            </div>
            {MOBILE_MORE_LINKS.map(({ to, label, Icon }) => (
              <NavLink
                key={to}
                to={to}
                role="menuitem"
                className={({ isActive }) => `mobile-more-link ${isActive ? "mobile-more-link--active" : ""}`}
              >
                <span className="mobile-more-link__icon"><Icon size={18} strokeWidth={2} /></span>
                <span>{label}</span>
              </NavLink>
            ))}
          </div>
        </>
      )}

      {/* --- Mobile bottom nav --- */}
      <nav className="mobile-bottom-nav" aria-label="ناوبری پایین">
        <NavLink to="/" end className={({ isActive }) => `mobile-nav-item ${isActive ? "mobile-nav-item--active" : ""}`}>
          <span className="mobile-nav-item__icon"><LayoutGrid size={20} strokeWidth={2} /></span>
          <span className="mobile-nav-item__label">خانه</span>
        </NavLink>
        <NavLink to="/leads" className={({ isActive }) => `mobile-nav-item ${isActive ? "mobile-nav-item--active" : ""}`}>
          <span className="mobile-nav-item__icon"><Users size={20} strokeWidth={2} /></span>
          <span className="mobile-nav-item__label">لیدها</span>
        </NavLink>
        <div className="mobile-nav-fab-slot"><QuickActionFab /></div>
        <NavLink to="/tasks" className={({ isActive }) => `mobile-nav-item ${isActive ? "mobile-nav-item--active" : ""}`}>
          <span className="mobile-nav-item__icon"><ListChecks size={20} strokeWidth={2} /></span>
          <span className="mobile-nav-item__label">وظایف</span>
        </NavLink>
        <NavLink to="/notifications" className={({ isActive }) => `mobile-nav-item ${isActive ? "mobile-nav-item--active" : ""}`}>
          <span className="mobile-nav-item__icon mobile-nav-item__icon--badged">
            <Bell size={20} strokeWidth={2} />
            {unread > 0 && (
              <span className="mobile-nav-badge" aria-label={`${unread} اعلان خوانده‌نشده`}>
                {unread > 9 ? "۹+" : faNum(unread)}
              </span>
            )}
          </span>
          <span className="mobile-nav-item__label">اعلان‌ها</span>
        </NavLink>
      </nav>

      {/* --- Main --- */}
      <main className="main-content" id="main-content">
        <header className="top-bar">
          <nav className="top-bar__breadcrumbs" aria-label="مسیر صفحه">
            <span className="top-bar__crumb-root">HadiFlow</span>
            <span className="top-bar__crumb-sep" aria-hidden="true">/</span>
            <span className="top-bar__crumb-current" aria-current="page">{currentCrumb}</span>
          </nav>
          <div className="top-bar__actions">
            <ThemeToggle />
            <NotificationBell />
          </div>
        </header>
        <div className="page-transition-wrapper">{children}</div>
      </main>

      <LiveRegion />
    </div>
  );
}
