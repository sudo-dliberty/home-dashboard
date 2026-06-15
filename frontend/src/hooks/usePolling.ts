import { useEffect, useRef, useState } from "react";

export interface PollingState<T> {
  data: T | null;
  error: string | null;
  lastFetchAt: number | null; // epoch ms
}

// Poll an async fetcher on an interval. Keeps last-good data on failure.
// `lastFetchAt` only advances on success so the UI can show a stale badge.
export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
): PollingState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastFetchAt, setLastFetchAt] = useState<number | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    let timer: ReturnType<typeof setTimeout>;

    const tick = async () => {
      try {
        const result = await fetcher();
        if (!mounted.current) return;
        setData(result);
        setError(null);
        setLastFetchAt(Date.now());
      } catch (e) {
        if (!mounted.current) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (mounted.current) {
          timer = setTimeout(tick, intervalMs);
        }
      }
    };

    tick();

    return () => {
      mounted.current = false;
      clearTimeout(timer!);
    };
    // We intentionally don't depend on fetcher reference to avoid restart loops.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs]);

  return { data, error, lastFetchAt };
}
