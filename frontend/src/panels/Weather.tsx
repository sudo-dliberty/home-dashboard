import { api, type WeatherResponse } from "../api";
import { StaleBadge } from "../components/StaleBadge";
import { WeatherIcon } from "../components/WeatherIcon";
import { usePolling } from "../hooks/usePolling";

const HOUR_FMT = new Intl.DateTimeFormat("en-US", {
  hour: "numeric",
  hour12: true,
  timeZone: "America/New_York",
});

function Chip({ on, label }: { on: boolean; label: string }) {
  return (
    <span
      className={`rounded-full px-3 py-1 font-medium ${
        on ? "bg-amber-500/20 text-amber-300" : "bg-zinc-800 text-zinc-500"
      }`}
      style={{ fontSize: "1.6vh" }}
    >
      {on ? `· ${label} ·` : label}
    </span>
  );
}

export function Weather() {
  const { data, error, lastFetchAt } = usePolling<WeatherResponse>(api.weather, 60_000);

  return (
    <div className="h-full px-5 py-4 flex flex-col bg-zinc-950 rounded-2xl border border-zinc-700">
      <div className="mb-2 flex items-baseline">
        <h2 className="font-semibold" style={{ fontSize: "2.6vh" }}>
          Astoria
        </h2>
        <StaleBadge
          lastFetchAt={lastFetchAt}
          staleAfterMs={180_000 /* 3× poll */}
          isStaleFromServer={data?.stale}
        />
      </div>

      {data ? (
        <>
          <div className="flex items-center gap-5">
            <WeatherIcon
              icon={data.current.icon}
              condition={data.current.condition}
              size="11vh"
              className="shrink-0 drop-shadow-[0_0_24px_rgba(0,0,0,0.4)]"
            />
            <div className="flex flex-col">
              <div className="font-semibold tabular-nums leading-none" style={{ fontSize: "9vh" }}>
                {Math.round(data.current.temp_f)}°
              </div>
              <div className="mt-1 text-zinc-200" style={{ fontSize: "2.2vh" }}>
                {data.current.condition}
              </div>
              <div className="mt-2 flex gap-2">
                <Chip on={data.summary.needs_coat} label="coat" />
                <Chip on={data.summary.needs_umbrella} label="umbrella" />
              </div>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-12 gap-1">
            {data.hourly.slice(0, 12).map((h) => (
              <div
                key={h.time}
                className="flex flex-col items-center rounded bg-zinc-900 py-1.5"
              >
                <div className="text-zinc-500" style={{ fontSize: "1.2vh" }}>
                  {HOUR_FMT.format(new Date(h.time))}
                </div>
                <WeatherIcon
                  condition={h.condition}
                  time={h.time}
                  size="2.6vh"
                  className="my-0.5"
                />
                <div className="font-semibold tabular-nums" style={{ fontSize: "1.8vh" }}>
                  {Math.round(h.temp_f)}°
                </div>
                <div
                  className={`tabular-nums ${
                    h.precip_prob >= 40 ? "text-sky-300" : "text-zinc-600"
                  }`}
                  style={{ fontSize: "1.2vh" }}
                >
                  {h.precip_prob}%
                </div>
              </div>
            ))}
          </div>
        </>
      ) : error ? (
        <div className="text-red-400 text-sm">Weather unavailable: {error}</div>
      ) : (
        <div className="text-zinc-500 text-sm">Loading…</div>
      )}
    </div>
  );
}
