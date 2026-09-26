import "./PageHeader.css";

/**
 * Standard page header: title, subtitle, optional count badge, optional action.
 */
export default function PageHeader({ title, subtitle, badge, action }) {
  return (
    <header className="page-header">
      <div className="page-header__text">
        <h1 className="page-header__title">
          {title}
          {badge != null && <span className="page-header__badge">{badge}</span>}
        </h1>
        {subtitle && <p className="page-header__subtitle">{subtitle}</p>}
      </div>
      {action && <div className="page-header__action">{action}</div>}
    </header>
  );
}
