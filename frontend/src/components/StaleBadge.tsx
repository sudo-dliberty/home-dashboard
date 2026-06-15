import { useEffect, useState } from "react";

export function StaleBadge({
  lastFetchAt,
  staleAfterMs,
  isStaleFromServer,
}: {
  lastFetchAt: number | null;
  staleAfterMs: number;
  isStaleFromServer?: boolean;
}) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 5_000);
    return () => clearInterval(t);
  }, []);

  if (!lastFetchAt) return null;
  const ageMs = now - lastFetchAt;
  const clientStale = ageMs > staleAfterMs;
  if (!clientStale && !isStaleFromServer) return null;

  const minutes = Math.floor(ageMs / 60_000);
  const label = isStaleFromServer
    ? "upstream stale"
    : minutes < 1
      ? "updating…"
      : `stale ${minutes}m`;

  return (
    <span className="ml-2 inline-block rounded bg-amber-700/70 px-2 py-0.5 text-xs font-medium text-amber-100">
      {label}
    </span>
  );
}
