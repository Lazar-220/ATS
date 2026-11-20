import { useSyncExternalStore } from "react";

import { parseRoute, type Route } from "./route";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

export function useRoute(): Route {
  // The hash string is the snapshot, so React sees a stable value between changes.
  const hash = useSyncExternalStore(subscribe, () => window.location.hash);
  return parseRoute(hash);
}
