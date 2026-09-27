import { useState, useEffect, useRef } from "react";
import { fmtNum, fmtCompactRial } from "../../utils/format";
import "./Charts.css";

/* ---------- Empty state ---------- */
export function EmptyChart({ label = "داده‌ای برای نمایش وجود ندارد" }) {
  return (
    <div className="chart-empty">
      <span>{label}</span>
    </div>
  );
}

/* ---------- Area / Line chart (time series) ---------- */
export function AreaChart({
  data,
  valueKey = "amount",
  height = 220,
  color = "var(--color-primary)",
  fmt = fmtCompactRial,
}) {
  const [hover, setHover] = useState(null);
  /* Rendered width of the chart, in CSS px — needed to clamp the tooltip
   * (see below). The SVG scales, so viewBox units alone are not enough. */
  const wrapRef = useRef(null);
  const [wrapW, setWrapW] = useState(0);
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => setWrapW(el.clientWidth);
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  if (!data || data.length === 0) return <EmptyChart />;

  const w = 640;
  const padX = 10;
  const padTop = 14;
  const padBottom = 26;
  const innerH = height - padTop - padBottom;
  const innerW = w - padX * 2;
  const max = Math.max(...data.map((d) => d[valueKey] || 0), 1);
  const stepX = data.length > 1 ? innerW / (data.length - 1) : innerW;

  const points = data.map((d, i) => ({
    x: padX + i * stepX,
    y: padTop + innerH - ((d[valueKey] || 0) / max) * innerH,
    d,
    i,
  }));

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const baseY = padTop + innerH;
  const areaPath = `${linePath} L${points[points.length - 1].x.toFixed(1)},${baseY} L${points[0].x.toFixed(1)},${baseY} Z`;

  // Show ~5 evenly spaced x labels to avoid crowding
  const labelEvery = Math.max(1, Math.ceil(data.length / 5));
  const active = hover != null ? points[hover] : null;
  /*
   * The tooltip is centred on the hovered point, so at either end of the
   * series half of it would spill outside the panel and get clipped. Clamp
   * its centre to the middle band of the chart: the box then always fits
   * inside the plot, and the dashed guide line still marks the exact point.
   */
  const TOOLTIP_HALF_PX = 95; // generous half-width, keeps «۱٫۲ میلیارد ریال» inside
  const rawPct = active ? (active.x / w) * 100 : 0;
  const edgePct = wrapW > 0 ? ((TOOLTIP_HALF_PX + 4) / wrapW) * 100 : 0;
  const clampedPct =
    active && edgePct < 50
      ? Math.min(100 - edgePct, Math.max(edgePct, rawPct))
      : rawPct;

  return (
    <div className="chart-wrap" dir="ltr" ref={wrapRef}>
      {active && (
        <div
          className="chart-tooltip"
          style={{ left: `${clampedPct}%` }}
        >
          <span className="chart-tooltip__label">{active.d.label}</span>
          <span className="chart-tooltip__value">{fmt(active.d[valueKey])}</span>
          {typeof active.d.count === "number" && (
            <span className="chart-tooltip__sub">{fmtNum(active.d.count)} مورد</span>
          )}
        </div>
      )}
      <svg
        viewBox={`0 0 ${w} ${height}`}
        className="chart-svg"
        onMouseLeave={() => setHover(null)}
      >
        {/* gridlines */}
        {[0.25, 0.5, 0.75].map((f) => (
          <line
            key={f}
            x1={padX}
            x2={w - padX}
            y1={padTop + innerH * f}
            y2={padTop + innerH * f}
            className="chart-grid"
          />
        ))}
        <line x1={padX} x2={w - padX} y1={baseY} y2={baseY} className="chart-axis" />

        <path d={areaPath} fill={color} className="chart-area" />
        <path d={linePath} fill="none" stroke={color} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />

        {/* hover guide */}
        {active && (
          <line x1={active.x} x2={active.x} y1={padTop} y2={baseY} className="chart-hoverline" />
        )}

        {/* points */}
        {points.map((p) => (
          <circle
            key={p.i}
            cx={p.x}
            cy={p.y}
            r={hover === p.i ? 5 : 3}
            fill={color}
            className="chart-dot"
          />
        ))}

        {/* x labels */}
        {points.map(
          (p) =>
            p.i % labelEvery === 0 && (
              <text key={`t${p.i}`} x={p.x} y={height - 8} className="chart-xlabel" textAnchor="middle">
                {p.d.label}
              </text>
            )
        )}

        {/* invisible hover targets */}
        {points.map((p) => (
          <rect
            key={`h${p.i}`}
            x={p.x - stepX / 2}
            y={0}
            width={stepX}
            height={height}
            fill="transparent"
            onMouseEnter={() => setHover(p.i)}
          />
        ))}
      </svg>
    </div>
  );
}

/* ---------- Horizontal bar chart (rankings) ---------- */
export function HBarChart({
  data,
  valueKey = "value",
  labelKey = "label",
  subKey,
  fmt = fmtNum,
  color = "var(--color-primary)",
}) {
  if (!data || data.length === 0) return <EmptyChart />;
  const max = Math.max(...data.map((d) => d[valueKey] || 0), 1);
  return (
    <div className="hbar-list">
      {data.map((d, i) => (
        <div className="hbar-row" key={i}>
          <div className="hbar-row__head">
            <span className="hbar-row__label">{d[labelKey]}</span>
            <span className="hbar-row__value">{fmt(d[valueKey])}</span>
          </div>
          <div className="hbar-row__track">
            <div
              className="hbar-row__fill"
              style={{ width: `${((d[valueKey] || 0) / max) * 100}%`, background: color }}
            />
          </div>
          {subKey && d[subKey] != null && (
            <div className="hbar-row__sub">{d[subKey]}</div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ---------- Donut chart (parts of a whole) ---------- */
export function DonutChart({ segments, centerValue, centerLabel }) {
  if (!segments || segments.length === 0) return <EmptyChart />;
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;
  const r = 56;
  const C = 2 * Math.PI * r;

  // Radial offsets are derived (not accumulated by mutating a counter
  // while mapping): mutation during render is unsafe under concurrent
  // rendering and defeats memoization.
  const dashes = segments.map((s) => ((s.value || 0) / total) * C);
  const laidOut = segments.map((s, i) => ({
    ...s,
    dash: dashes[i],
    offset: dashes.slice(0, i).reduce((sum, d) => sum + d, 0),
  }));

  return (
    <div className="donut-wrap">
      <svg viewBox="0 0 160 160" className="donut-svg" dir="ltr">
        <circle cx="80" cy="80" r={r} fill="none" className="donut-track" strokeWidth={18} />
        {laidOut.map((s, i) => (
          <circle
            key={i}
            cx="80"
            cy="80"
            r={r}
            fill="none"
            stroke={s.color}
            strokeWidth={18}
            strokeDasharray={`${s.dash} ${C - s.dash}`}
            strokeDashoffset={-s.offset}
            transform="rotate(-90 80 80)"
            strokeLinecap="butt"
          />
        ))}
        <text x="80" y="76" textAnchor="middle" className="donut-center-value">{centerValue}</text>
        <text x="80" y="96" textAnchor="middle" className="donut-center-label">{centerLabel}</text>
      </svg>
      <div className="donut-legend">
        {segments.map((s, i) => (
          <div className="donut-legend__item" key={i}>
            <span className="donut-legend__dot" style={{ background: s.color }} />
            <span className="donut-legend__label">{s.label}</span>
            <span className="donut-legend__value">{fmtNum(s.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------- Funnel (pipeline stages) ---------- */
export function FunnelChart({ stages, statusLabel, statusColor }) {
  if (!stages || stages.length === 0) return <EmptyChart />;
  const max = Math.max(...stages.map((s) => s.count || 0), 1);
  const total = stages.reduce((a, s) => a + (s.count || 0), 0);
  return (
    <div className="funnel-wrap">
      <div className="funnel-total">{fmtNum(total)} پرونده فعال</div>
      <div className="funnel-list">
        {stages.map((s, i) => (
          <div className="funnel-row" key={s.status} style={{ "--stagger": i }}>
            <span className="funnel-row__label">{statusLabel ? statusLabel(s.status) : s.status}</span>
            <div className="funnel-row__track">
              <div
                className="funnel-row__fill"
                style={{
                  width: `${((s.count || 0) / max) * 100}%`,
                  background: statusColor ? statusColor(s.status) : "var(--color-primary)",
                }}
              />
            </div>
            <span className="funnel-row__count">{fmtNum(s.count)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
