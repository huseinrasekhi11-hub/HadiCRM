import { useEffect, useRef } from "react";

/**
 * Sentinel-based infinite scroll. Renders children; when the sentinel
 * intersects the viewport and more data exists, calls onReachEnd().
 */
export default function InfiniteScroll({ onReachEnd, hasMore, loading, children }) {
  const sentinelRef = useRef(null);

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node || !hasMore || loading) return;
    const observer = new IntersectionObserver(
      (entries) => entries.forEach((entry) => entry.isIntersecting && onReachEnd()),
      { rootMargin: "200px" }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, loading, onReachEnd]);

  return (
    <>
      {children}
      <div ref={sentinelRef} aria-hidden="true" style={{ height: 1 }} />
    </>
  );
}
