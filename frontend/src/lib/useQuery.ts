import { useCallback, useEffect, useRef, useState } from "react";

export interface QueryState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  /** Re-run the query now (keeps current data while loading). */
  reload: () => void;
  setData: (updater: T | null | ((current: T | null) => T | null)) => void;
}

export interface QueryOptions {
  /** Poll interval in ms; 0/undefined disables polling. */
  pollMs?: number;
  enabled?: boolean;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Small data-fetching hook: aborts in-flight requests on change/unmount,
 * optional polling (paused while the tab is hidden).
 */
export function useQuery<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
  options: QueryOptions = {},
): QueryState<T> {
  const { pollMs, enabled = true } = options;
  const [data, setDataState] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(enabled);
  const [tick, setTick] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const key = JSON.stringify(deps);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    fetcherRef
      .current(controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setDataState(result);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(errorMessage(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [key, tick, enabled]);

  useEffect(() => {
    if (!pollMs || !enabled) return;
    const id = window.setInterval(() => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      setTick((value) => value + 1);
    }, pollMs);
    return () => window.clearInterval(id);
  }, [pollMs, enabled]);

  const reload = useCallback(() => setTick((value) => value + 1), []);
  const setData = useCallback((updater: T | null | ((current: T | null) => T | null)) => {
    setDataState((current) => (typeof updater === "function" ? (updater as (c: T | null) => T | null)(current) : updater));
  }, []);

  return { data, error, loading, reload, setData };
}
