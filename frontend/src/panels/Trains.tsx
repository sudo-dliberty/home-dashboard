import { api, type TrainArrival, type TrainsResponse } from "../api";
import { RouteBullet } from "../components/RouteBullet";
import { StaleBadge } from "../components/StaleBadge";
import { usePolling } from "../hooks/usePolling";

// Arrival board: each direction lists its next few trains in arrival
// order, one train per row — route bullet plus a big countdown.
const MAX_ROWS = 4;

function Minutes({ value }: { value: number }) {
  // Keyed on the value so a changed countdown slides gently into place.
  if (value < 1) {
    return (
      <span key="now" className="animate-settle font-semibold type-title" style={{ color: "var(--system-green)" }}>
        Now
      </span>
    );
  }
  return (
    <span key={value} className="inline-flex animate-settle items-baseline gap-[0.2em]">
      <span className="font-semibold tabular-nums type-title">{value}</span>
      <span className="font-semibold type-caption" style={{ fontSize: "0.5em", color: "var(--label-secondary)" }}>
        min
      </span>
    </span>
  );
}

function Row({ arrival, isLast }: { arrival: TrainArrival; isLast: boolean }) {
  return (
    <li className="flex items-center gap-[1.4vh]">
      <RouteBullet route={arrival.route} size="3.6vh" />
      <div
        className={`flex min-w-0 flex-1 items-center py-[1.1vh] ${isLast ? "" : "border-b"}`}
        style={{ borderColor: "var(--separator)", fontSize: "3.2vh" }}
      >
        <Minutes value={arrival.minutes} />
      </div>
    </li>
  );
}

function Direction({ label, arrivals }: { label: string; arrivals: TrainArrival[] }) {
  const rows = [...arrivals].sort((x, y) => x.minutes - y.minutes).slice(0, MAX_ROWS);
  return (
    <section className="min-w-0 flex-1">
      <h3
        className="mb-[0.4vh] truncate font-semibold type-eyebrow"
        style={{ fontSize: "1.3vh", color: "var(--label-secondary)" }}
      >
        {label}
      </h3>
      {rows.length === 0 ? (
        <div className="py-[1vh] type-headline" style={{ fontSize: "1.8vh", color: "var(--label-tertiary)" }}>
          No trains
        </div>
      ) : (
        <ul>
          {rows.map((a, i) => (
            <Row key={`${a.route}-${a.arrival}`} arrival={a} isLast={i === rows.length - 1} />
          ))}
        </ul>
      )}
    </section>
  );
}

export function Trains() {
  const { data, error, lastFetchAt } = usePolling<TrainsResponse>(api.trains, 30_000);

  return (
    <div className="material-panel flex h-full flex-col overflow-hidden px-[2.4vh] py-[2.2vh]">
      <div className="mb-[1.4vh] flex items-center">
        <h2 className="font-semibold type-headline" style={{ fontSize: "2.2vh" }}>
          {data?.station ?? "Trains"}
        </h2>
        <StaleBadge lastFetchAt={lastFetchAt} staleAfterMs={90_000 /* 3× poll */} isStaleFromServer={data?.stale} />
      </div>

      {data ? (
        <div className="flex gap-[3vh]">
          <Direction label={data.north.label} arrivals={data.north.arrivals} />
          <Direction label={data.south.label} arrivals={data.south.arrivals} />
        </div>
      ) : (
        <div className="m-auto type-headline" style={{ fontSize: "1.9vh", color: "var(--label-secondary)" }}>
          {error ? "Trains unavailable" : "Loading…"}
        </div>
      )}
    </div>
  );
}
