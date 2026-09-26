import { api } from "./client";

const BASE = "/dashboard/charts";

export async function getChartDailySales({ days = 30, calendar = "jalali", dateFrom, dateTo } = {}) {
  const res = await api.get(`${BASE}/daily-sales`, {
    params: { days, calendar, date_from: dateFrom, date_to: dateTo },
  });
  return res.data;
}

export async function getChartSalesByUser({ days } = {}) {
  const res = await api.get(`${BASE}/sales-by-user`, { params: { days } });
  return res.data;
}

export async function getChartLeadsByUser() {
  const res = await api.get(`${BASE}/leads-by-user`);
  return res.data;
}

export async function getChartConversion() {
  const res = await api.get(`${BASE}/conversion`);
  return res.data;
}

export async function getChartReferralsReceived() {
  const res = await api.get(`${BASE}/referrals-received`);
  return res.data;
}

export async function getChartReferralsBetweenUsers() {
  const res = await api.get(`${BASE}/referrals-between-users`);
  return res.data;
}

export async function getChartSalesTrend({ days = 90, granularity = "day", calendar = "jalali" } = {}) {
  const res = await api.get(`${BASE}/sales-trend`, { params: { days, granularity, calendar } });
  return res.data;
}

export async function getChartTopProducts({ days } = {}) {
  const res = await api.get(`${BASE}/top-products`, { params: { days } });
  return res.data;
}
