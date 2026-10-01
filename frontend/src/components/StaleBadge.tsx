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
    ? "Delayed data"
    : minutes < 1
      ? "Updating…"
      : `Updated ${minutes}m ago`;

  return (
    <span
      className="ml-auto inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 font-semibold type-caption"
      style={{
        fontSize: "1.3vh",
        color: "var(--system-orange)",
        background: "rgba(255,159,10,0.16)",
      }}
    >
      <span
        className="inline-block h-[0.55em] w-[0.55em] rounded-full"
        style={{ background: "var(--system-orange)" }}
      />
      {label}
    </span>
  );
}
