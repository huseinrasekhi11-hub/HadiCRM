import { useEffect, useState } from "react";
import {
  BarChart3, TrendingUp, Target, Users, UserCheck, CalendarRange,
} from "lucide-react";
import {
  getChartDailySales, getChartSalesByUser, getChartLeadsByUser,
  getChartConversion, getChartReferralsReceived, getChartReferralsBetweenUsers,
  getChartSalesTrend, getChartTopProducts,
} from "../api/charts";
import { useAuth } from "../context/AuthContext";
import { getUsers } from "../api/client";
import AppShell from "../components/AppShell";
import AccessDenied from "../components/AccessDenied";
import { isAdminOnly } from "../permissions";
import {
  AreaChart, HBarChart, DonutChart,
  fmtNum, fmtCompactRial, fmtRial,
} from "../components/charts/Charts";
import "./Analytics.css";

/* ---------- Panel wrapper (same convention as Dashboard.jsx) ---------- */
function Panel({ title, icon: Icon, subtitle, actions, children, wide, allowOverflow }) {
  return (
    <section className={`dash-panel ${wide ? "dash-panel--wide" : ""} ${allowOverflow ? "dash-panel--allow-overflow" : ""}`}>
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

export default function Analytics() {
  const { user } = useAuth();
  const allowed = isAdminOnly(user?.role);

  // The calendar is always Jalali — there is no Gregorian mode to switch to.
  const [trendGran, setTrendGran] = useState("day");
  const [charts, setCharts] = useState({});
  const [staffIds, setStaffIds] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  /*
   * Per-person statistics describe the sales floor, so supervisory accounts
   * are excluded. An admin or CEO appearing in «توزیع پرونده‌ها» or
   * «ارجاع‌ها» distorts every comparison: they hold leads only transiently
   * while routing them, and their referral counts are routing activity
   * rather than sales performance.
   */
  useEffect(() => {
    if (!allowed) return;
    let cancelled = false;
    getUsers()
      .then((users) => {
        if (cancelled) return;
        setStaffIds(new Set(users.filter((u) => !isAdminOnly(u.role)).map((u) => u.id)));
      })
      // If the roster cannot be read, show the unfiltered data rather than
      // an empty chart — a slightly wider set beats no data at all.
      .catch(() => { if (!cancelled) setStaffIds(null); });
    return () => { cancelled = true; };
  }, [allowed]);

  useEffect(() => {
    if (!allowed) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    Promise.all([
      getChartDailySales({ days: 30, calendar: "jalali" }).catch(() => null),
      getChartSalesByUser().catch(() => null),
      getChartLeadsByUser().catch(() => null),
      getChartConversion().catch(() => null),
      getChartReferralsReceived().catch(() => null),
      getChartReferralsBetweenUsers().catch(() => null),
      getChartSalesTrend({ days: 90, granularity: trendGran, calendar: "jalali" }).catch(() => null),
      getChartTopProducts().catch(() => null),
    ])
      .then(([dailySales, salesByUser, leadsByUser, conversion, referralsReceived, referralsBetween, salesTrend, topProducts]) => {
        if (cancelled) return;
        setCharts({ dailySales, salesByUser, leadsByUser, conversion, referralsReceived, referralsBetween, salesTrend, topProducts });
      })
      .catch(() => { if (!cancelled) setError("دریافت نمودارها با خطا مواجه شد."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [trendGran, allowed]);

  if (!allowed) {
    return (
      <AppShell>
        <AccessDenied />
      </AppShell>
    );
  }

  /* Keep only rows belonging to non-supervisory staff. */
  const onlyStaff = (rows) => {
    if (!Array.isArray(rows)) return [];
    if (!staffIds) return rows;
    return rows.filter((r) => r.user_id == null || staffIds.has(r.user_id));
  };
  /* Referral pairs need BOTH ends to be sales staff to count. */
  const staffReferralPairs = (rows) => {
    if (!Array.isArray(rows)) return [];
    if (!staffIds) return rows;
    return rows.filter(
      (r) =>
        (r.from_user_id == null || staffIds.has(r.from_user_id)) &&
        (r.to_user_id == null || staffIds.has(r.to_user_id))
    );
  };

  const conversionSegments = charts.conversion
    ? [
        { label: "باز", value: charts.conversion.open_leads, color: "var(--color-primary)" },
        { label: "فاکتور", value: charts.conversion.won_leads, color: "var(--color-success)" },
        { label: "ناموفق", value: charts.conversion.lost_leads, color: "var(--color-danger)" },
      ]
    : [];

  return (
    <AppShell>
      <div className="analytics-container">
        <header className="analytics-header">
          <div className="analytics-header__title">
            <BarChart3 size={20} />
            <h1>تحلیل‌ها و نمودارهای فروش</h1>
          </div>
        </header>

        {error && <div className="alert-banner alert-banner--error">{error}</div>}

        {loading && (
          <div className="dash-skeleton">
            <div className="skeleton" style={{ height: 220 }} />
            <div className="skeleton" style={{ height: 220 }} />
            <div className="skeleton" style={{ height: 220 }} />
          </div>
        )}

        {!loading && !error && (
          <>
            {/* The panel body is overflow:hidden (rounded corners), which used
                to clip the tooltip of a point near either edge. */}
            <Panel title="فروش روزانه" icon={CalendarRange} subtitle="۳۰ روز گذشته (ریال)" wide allowOverflow>
              <AreaChart data={charts.dailySales} valueKey="amount" fmt={fmtCompactRial} color="var(--color-primary)" />
            </Panel>

            <Panel
              title="روند فروش"
              icon={TrendingUp}
              subtitle="۹۰ روز گذشته"
              wide
              allowOverflow
              actions={
                <div className="seg">
                  {[["day", "روز"], ["week", "هفته"], ["month", "ماه"]].map(([v, l]) => (
                    <button key={v} className={`seg__btn ${trendGran === v ? "seg__btn--active" : ""}`} onClick={() => setTrendGran(v)}>{l}</button>
                  ))}
                </div>
              }
            >
              <AreaChart data={charts.salesTrend} valueKey="amount" fmt={fmtCompactRial} color="var(--color-success)" />
            </Panel>

            <div className="dash-two-col">
              <Panel title="نرخ تبدیل" icon={Target} subtitle={charts.conversion ? `${fmtNum(charts.conversion.conversion_rate)}٪ از پرونده‌های بسته‌شده` : ""}>
                <DonutChart
                  segments={conversionSegments}
                  centerValue={charts.conversion ? `${fmtNum(charts.conversion.conversion_rate)}٪` : "—"}
                  centerLabel="نرخ تبدیل"
                />
              </Panel>

              <Panel title="فروش به تفکیک کارشناس" icon={Users}>
                <HBarChart
                  data={onlyStaff(charts.salesByUser).map((r) => ({
                    label: r.full_name || `#${r.user_id}`,
                    value: r.total_sales,
                    sub: `${fmtNum(r.won_count)} فاکتور · میانگین ${fmtCompactRial(r.average_sale)}`,
                  }))}
                  valueKey="value"
                  subKey="sub"
                  fmt={fmtCompactRial}
                  color="var(--color-primary)"
                />
              </Panel>
            </div>

            <div className="dash-two-col">
              <Panel title="پرفروش‌ترین کالاها" icon={Target} subtitle="ریال">
                {charts.topProducts?.products?.length ? (
                  <>
                    <HBarChart
                      data={charts.topProducts.products.map((p) => ({
                        label: p.product_name,
                        value: p.total_sales,
                        sub: `${fmtNum(p.lead_count)} پرونده`,
                      }))}
                      valueKey="value"
                      subKey="sub"
                      fmt={fmtCompactRial}
                      color="var(--color-warning)"
                    />
                    {charts.topProducts.unattributed_amount > 0 && (
                      <div className="dash-note">
                        {fmtRial(charts.topProducts.unattributed_amount)} فروش تاریخی بدون قلم ساختاریافته (خارج از نمودار)
                      </div>
                    )}
                  </>
                ) : (
                  <div className="dash-empty">داده‌ای وجود ندارد.</div>
                )}
              </Panel>

              <Panel title="توزیع پرونده‌ها" icon={Users}>
                <HBarChart
                  data={onlyStaff(charts.leadsByUser).map((r) => ({
                    label: r.full_name || `#${r.user_id}`,
                    value: r.total_leads,
                    sub: `${fmtNum(r.open_leads)} باز · ${fmtNum(r.won_leads)} موفق · ${fmtNum(r.lost_leads)} ناموفق`,
                  }))}
                  valueKey="value"
                  subKey="sub"
                  fmt={fmtNum}
                  color="var(--color-primary)"
                />
              </Panel>
            </div>

            <div className="dash-two-col">
              <Panel title="ارجاع‌های دریافت‌شده" icon={UserCheck}>
                <HBarChart
                  data={onlyStaff(charts.referralsReceived).map((r) => ({
                    label: r.full_name || `#${r.user_id}`,
                    value: r.received_count,
                  }))}
                  valueKey="value"
                  fmt={fmtNum}
                  color="var(--color-success)"
                />
              </Panel>

              <Panel title="ارجاع‌های بین کارشناسان" icon={Users}>
                {staffReferralPairs(charts.referralsBetween).length ? (
                  <div className="referral-list">
                    {staffReferralPairs(charts.referralsBetween).map((r, i) => (
                      <div className="referral-row" key={i}>
                        <span className="referral-row__from">{r.from_full_name || `#${r.from_user_id}`}</span>
                        <span className="referral-row__arrow">←</span>
                        <span className="referral-row__to">{r.to_full_name || `#${r.to_user_id}`}</span>
                        <span className="referral-row__count">{fmtNum(r.count)}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="dash-empty">ارجاعی ثبت نشده است.</div>
                )}
              </Panel>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}
