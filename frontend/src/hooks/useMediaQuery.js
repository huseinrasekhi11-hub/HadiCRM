import { useCallback, useSyncExternalStore } from "react";

/**
 * Subscribe to a CSS media query.
 *
 * Implemented with `useSyncExternalStore` rather than state + effect: the
 * media query list is an external store, and syncing it through an effect
 * meant the first paint used the value read during render, then immediately
 * re-rendered after the effect ran (and any change between render and
 * subscription was missed).
 */
export default function useMediaQuery(query) {
  const subscribe = useCallback(
    (onStoreChange) => {
      const mql = window.matchMedia(query);
      mql.addEventListener("change", onStoreChange);
      return () => mql.removeEventListener("change", onStoreChange);
    },
    [query],
  );

  const getSnapshot = useCallback(() => window.matchMedia(query).matches, [query]);

  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
