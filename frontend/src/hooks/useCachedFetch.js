import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Fetch with graceful refresh: previous data stays visible while reloading,
 * so pull-to-refresh / filter changes never flash an empty screen.
 */
export function useCachedFetch(fetchFn, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await fetchFn();
      if (mounted.current) setData(result);
    } catch (e) {
      if (mounted.current) setError(e?.message || "خطا در دریافت اطلاعات");
    } finally {
      if (mounted.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => { reload(); }, [reload]);

  return { data, loading, error, reload, hasData: data != null };
}
