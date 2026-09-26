import { HEALTH_META, healthLabel, healthColor } from "../leadStatus";
import "./HealthBadge.css";

export default function HealthBadge({ health, size = "md" }) {
  if (!health || !HEALTH_META[health]) return null;

  const color = healthColor(health);
  const label = healthLabel(health);
  const isCritical = health === "critical" || health === "at_risk";

  return (
    <div 
      className={`health-badge health-badge--${size} ${isCritical ? 'health-badge--pulse' : ''}`}
      style={{ "--health-color": color }}
      title={label}
    >
      <div className="health-badge__dot-wrapper">
        <div className="health-badge__dot" />
        {isCritical && <div className="health-badge__ping" />}
      </div>
      {size === "lg" && <span className="health-badge__label">{label}</span>}
    </div>
  );
}
