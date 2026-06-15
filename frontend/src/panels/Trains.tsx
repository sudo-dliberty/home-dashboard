import { useEffect, useRef, useState } from "react";
import { api, type TrainArrival, type TrainsResponse } from "../api";
import { RouteBullet } from "../components/RouteBullet";
import { StaleBadge } from "../components/StaleBadge";
import { usePolling } from "../hooks/usePolling";

// Derive the "· N / W" subtitle from the routes actually present in the
// arrivals (we don't have the selected-routes list on this response).
function routeSummary(data: TrainsResponse): string {
  const routes = new Set<string>();
  for (const a of [...data.north.arrivals, ...data.south.arrivals]) routes.add(a.route);
  return [...routes].sort().join(" / ");
}

function ArrivalRow({ a }: { a: TrainArrival }) {
  const label = a.minutes < 1 ? "Now" : `${a.minutes} min`;
  return (
    <li className="flex items-baseline gap-3 py-1">
      <RouteBullet route={a.route} size="2.2em" />
      <span className="font-semibold tabular-nums" style={{ fontSize: "2.8vh" }}>
        {label}
      </span>
    </li>
  );
}

function Column({
  title,
  arrivals,
}: {
  title: string;
  arrivals: TrainArrival[];
}) {
  return (
    <div className="flex-1 min-w-0">
      <div className="mb-2 text-zinc-400" style={{ fontSize: "1.6vh" }}>
        {title}
      </div>
      {arrivals.length === 0 ? (
        <div className="text-zinc-500" style={{ fontSize: "2vh" }}>
          —
        </div>
      ) : (
        <ul className="space-y-1">
          {arrivals.slice(0, 4).map((a, i) => (
            <ArrivalRow key={`${a.route}-${a.arrival}-${i}`} a={a} />
          ))}
        </ul>
      )}
    </div>
  );
}

export function Trains() {
  const { data, error, lastFetchAt } = usePolling<TrainsResponse>(api.trains, 30_000);

  // Drive an MTA-style update flash whenever `fetched_at` advances.
  // Bumping `pulseKey` remounts the overlay div so the CSS animation
  // replays from frame 0 instead of being a no-op on its second trigger.
  const prevFetched = useRef<string | null>(null);
  const [pulseKey, setPulseKey] = useState(0);
  useEffect(() => {
    if (!data?.fetched_at) return;
    if (prevFetched.current !== null && prevFetched.current !== data.fetched_at) {
      setPulseKey((k) => k + 1);
    }
    prevFetched.current = data.fetched_at;
  }, [data?.fetched_at]);

  return (
    <div className="relative h-full px-5 py-4 flex flex-col bg-zinc-950 rounded-2xl overflow-hidden border border-zinc-700">
      {/* Update flash overlay. `key` change replays the animation. */}
      <div
        key={pulseKey}
        className="pointer-events-none absolute inset-0 animate-flash rounded-2xl"
        aria-hidden
      />
      <div className="mb-2 flex items-baseline">
        <h2 className="font-semibold" style={{ fontSize: "2.6vh" }}>
          {data?.station ?? "Trains"}
          {data && routeSummary(data) && (
            <span className="text-zinc-500 font-normal"> · {routeSummary(data)}</span>
          )}
        </h2>
        <StaleBadge
          lastFetchAt={lastFetchAt}
          staleAfterMs={90_000 /* 3× poll */}
          isStaleFromServer={data?.stale}
        />
      </div>

      {data ? (
        <div className="flex flex-1 gap-6">
          <Column title={`→ ${data.north.label}`} arrivals={data.north.arrivals} />
          <Column title={`→ ${data.south.label}`} arrivals={data.south.arrivals} />
        </div>
      ) : error ? (
        <div className="text-red-400 text-sm">Trains unavailable: {error}</div>
      ) : (
        <div className="text-zinc-500 text-sm">Loading…</div>
      )}
    </div>
  );
}
