import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Sun, Sunset, Moon, Users, UserCheck, ListChecks, ArrowUpRight,
  Clock, AlertTriangle, Sparkles, Flame, Inbox, AlertOctagon,
  Target, Activity, BarChart3,
} from "lucide-react";
import { getDashboard } from "../api/client";
import { useAuth } from "../hooks/useAuth";
import AppShell from "../components/AppShell";
import { useCountUp } from "../hooks/useCountUp";
import { statusLabel, statusColor } from "../leadStatus";
import { FunnelChart } from "../components/charts/Charts";
import { fmtNum } from "../utils/format";
import "./Dashboard.css";

const getGreeting = () => {
  const hour = new Date().getHours();
  if (hour < 12) return { text: "صبح بخیر", Icon: Sun, time: "morning" };
  if (hour < 18) return { text: "ظهر بخیر", Icon: Sunset, time: "afternoon" };
  return { text: "شب بخیر", Icon: Moon, time: "evening" };
};

/* ---------- KPI card with count-up ---------- */
function StatCard({ label, value, icon: Icon, tone = "neutral", to, hint }) {
  const count = useCountUp(value ?? 0);
  const body = (
    <>
      <div className="stat-card__top">
        <span className={`stat-card__icon stat-card__icon--${tone}`}><Icon size={16} /></span>
        {to && <ArrowUpRight size={14} className="stat-card__arrow" />}
      </div>
      <div className="stat-card__value">{fmtNum(count)}</div>
      <div className="stat-card__label">{label}</div>
      {hint && <div className="stat-card__hint">{hint}</div>}
    </>
  );
  return to ? (
    <Link to={to} className={`stat-card stat-card--${tone}`}>{body}</Link>
  ) : (
    <div className={`stat-card stat-card--${tone}`}>{body}</div>
  );
}

/* ---------- Panel wrapper ---------- */
function Panel({ title, icon: Icon, subtitle, actions, children, wide }) {
  return (
    <section className={`dash-panel ${wide ? "dash-panel--wide" : ""}`}>
      <div className="dash-panel__header">
        <div className="dash-panel__title">
          {Icon && <Icon size={15} className="dash-panel__title-icon" />}
          <span>{title}</span>
          {subtitle && <span className="dash-panel__subtitle">{subtitle}</span>}
        </div>
        {actions && <div className="dash-panel__actions">{actions}</div>}
      </div>
      <div className="dash-panel__body">{children}</div>
    </section>
  );
}

/* ======================================================================== */
/* REP DASHBOARD — attention-driven, action-first                           */
/* ======================================================================== */
function RepDashboard({ data }) {
  return (
    <div className="dash-body">
      <div className="dash-kpi-grid">
        <StatCard label="پیگیری امروز" value={data.today_followups} icon={Clock} tone="primary" to="/leads?filter=today_followup" />
        <StatCard label="پیگیری عقب‌افتاده" value={data.overdue_followups} icon={AlertTriangle} tone="danger" to="/leads?filter=overdue" />
        <StatCard label="لید جدید" value={data.new_leads} icon={Sparkles} tone="success" to="/leads?filter=new" />
        <StatCard label="بحرانی" value={data.critical_leads} icon={Flame} tone="warning" to="/leads?filter=critical" />
        <StatCard label="وظایف امروز" value={data.today_tasks} icon={ListChecks} tone="neutral" to="/tasks" />
        <StatCard label="وظایف عقب‌افتاده" value={data.overdue_tasks} icon={AlertOctagon} tone="danger" to="/tasks" />
      </div>

      <div className="dash-two-col">
        <Panel title="آخرین فعالیت‌ها" icon={Activity}>
          {data.recent_activity_feed?.length ? (
            <div className="feed-list">
              {data.recent_activity_feed.map((a) => (
                <Link key={a.id} to={`/leads/${a.lead_id}`} className="feed-item">
                  <span className="feed-item__title">{a.title}</span>
                  <span className="feed-item__sub">{a.customer_name}</span>
                </Link>
              ))}
            </div>
          ) : (
            <div className="dash-empty">فعالیتی ثبت نشده است.</div>
          )}
        </Panel>

        <Panel title="ارجاع‌های اخیر به شما" icon={UserCheck}>
          {data.recently_assigned?.length ? (
            <div className="feed-list">
              {data.recently_assigned.map((r, i) => (
                <Link key={i} to={`/leads/${r.lead_id}`} className="feed-item">
                  <span className="feed-item__title">{r.customer_name}</span>
                  <span className="feed-item__sub">ارجاع‌شده به شما</span>
                </Link>
              ))}
            </div>
          ) : (
            <div className="dash-empty">ارجاع جدیدی ندارید.</div>
          )}
        </Panel>
      </div>
    </div>
  );
}

/* ======================================================================== */
/* MANAGER DASHBOARD — operational health (admin sales analytics live at    */
/* /analytics, see Analytics.jsx, to avoid duplicating the same charts)     */
/* ======================================================================== */
function ManagerDashboard({ data }) {
  return (
    <div className="dash-body">
      {/* ---- Operational KPIs ---- */}
      <div className="dash-kpi-grid">
        <StatCard label="کل پرونده‌ها" value={data.leads} icon={Users} tone="primary" to="/leads" />
        <StatCard label="نیاز به توجه" value={data.needs_attention} icon={AlertTriangle} tone="warning" to="/leads?filter=critical" />
        <StatCard label="پیگیری عقب‌افتاده" value={data.overdue_leads} icon={Clock} tone="danger" to="/leads?filter=overdue" />
        <StatCard label="بدون فعالیت" value={data.inactive_leads} icon={Inbox} tone="neutral" to="/leads?filter=no_activity" />
        <StatCard label="ارجاع اضطراری" value={data.escalated_leads} icon={AlertOctagon} tone="danger" to="/leads?filter=escalated" />
        <StatCard label="کاربران فعال" value={data.users} icon={UserCheck} tone="neutral" />
      </div>

      {/* ---- Pipeline ---- */}
      {/* نرخ تبدیل و سایر نمودارهای فروش اکنون در صفحه‌ی /analytics هستند
          (فقط ادمین/مدیرعامل) — برای پرهیز از تکرار همان نمودار در دو صفحه. */}
      <Panel title="قیف فروش" icon={Target}>
        <FunnelChart stages={data.pipeline} statusLabel={statusLabel} statusColor={statusColor} />
      </Panel>

      {/* ---- Salesperson performance table ---- */}
      <Panel title="عملکرد کارشناسان" icon={Users} subtitle="ماه جاری">
        {data.salesperson_performance?.length ? (
          <div className="perf-table-wrap">
            <table className="perf-table">
              <thead>
                <tr>
                  <th>کارشناس</th>
                  <th>پرونده باز</th>
                  <th>فاکتور</th>
                  <th>ناموفق</th>
                </tr>
              </thead>
              <tbody>
                {data.salesperson_performance.map((p) => (
                  <tr key={p.user_id}>
                    <td className="perf-table__name">{p.full_name}</td>
                    <td>{fmtNum(p.open_leads)}</td>
                    <td className="perf-table__won">{fmtNum(p.won_this_month)}</td>
                    <td className="perf-table__lost">{fmtNum(p.lost_this_month)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="dash-empty">کارشناسی ثبت نشده است.</div>
        )}
      </Panel>

    </div>
  );
}

/* ======================================================================== */
/* MAIN                                                                     */
/* ======================================================================== */
export default function Dashboard() {
  const { user } = useAuth();
  const isAdmin = ["admin", "ceo"].includes(user?.role);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const { text: greeting, Icon: GreetingIcon, time } = getGreeting();

  useEffect(() => {
    getDashboard()
      .then(setData)
      .catch(() => setError("دریافت داشبورد با خطا مواجه شد."))
      .finally(() => setLoading(false));
  }, []);

  const isManagerView = data && Array.isArray(data.pipeline);

  return (
    <AppShell>
      <div className="dashboard-container">
        <header className="dash-header">
          <div className={`dash-header__badge dash-header__badge--${time}`}>
            <GreetingIcon size={14} />
            <span>{greeting}</span>
          </div>
          <h1 className="dash-header__title">
            خوش آمدید، <span className="dash-header__name">{user?.full_name}</span>
          </h1>
          <p className="dash-header__subtitle">
            {isManagerView ? "نمای مدیریتی — سلامت عملیات پرونده‌ها" : "نمای کارشناس — آنچه امروز به توجه شما نیاز دارد"}
          </p>
          {isManagerView && isAdmin && (
            <Link to="/analytics" className="dash-header__analytics-link">
              <BarChart3 size={14} />
              <span>مشاهده‌ی تحلیل‌ها و نمودارهای فروش</span>
            </Link>
          )}
        </header>

        {loading && (
          <div className="dash-skeleton">
            <div className="skeleton" style={{ height: 90 }} />
            <div className="skeleton" style={{ height: 220 }} />
            <div className="skeleton" style={{ height: 220 }} />
          </div>
        )}
        {error && <div className="alert-banner alert-banner--error">{error}</div>}

        {!loading && !error && data && (
          isManagerView
            ? <ManagerDashboard data={data} />
            : <RepDashboard data={data} />
        )}
      </div>
    </AppShell>
  );
}
