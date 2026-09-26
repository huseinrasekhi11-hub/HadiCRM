import "./EmptyState.css";

/**
 * The single empty-state primitive for the whole product.
 */
export default function EmptyState({ icon: Icon, title, subtitle, action, compact = false }) {
  return (
    <div className={`empty-state ${compact ? "empty-state--compact" : ""}`}>
      {Icon && (
        <div className="empty-state__icon-wrap">
          <Icon size={compact ? 20 : 26} className="empty-state__icon" />
        </div>
      )}
      <h3 className="empty-state__title">{title}</h3>
      {subtitle && <p className="empty-state__subtitle">{subtitle}</p>}
      {action && <div className="empty-state__action">{action}</div>}
    </div>
  );
}
