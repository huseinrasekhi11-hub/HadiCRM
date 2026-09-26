import "./Skeleton.css";

export function Skeleton({ className = "", style }) {
  return <div className={`skeleton ${className}`} style={style} aria-hidden="true" />;
}

export function SkeletonList({ rows = 5, rowHeight = 64 }) {
  return (
    <div className="skeleton-list" role="status" aria-label="در حال بارگذاری">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} style={{ height: rowHeight }} />
      ))}
    </div>
  );
}
