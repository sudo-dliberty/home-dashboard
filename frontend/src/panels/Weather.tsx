import { useMemo } from "react";
import { Navigation, ThermometerSnowflake, Umbrella } from "lucide-react";
import { api, type WeatherResponse } from "../api";
import { StaleBadge } from "../components/StaleBadge";
import { WeatherIcon } from "../components/WeatherIcon";
import { usePolling } from "../hooks/usePolling";
import { useSettings } from "../settings/SettingsContext";

// Precip chance is only worth showing (in cyan) once it's meaningful, the
// same way Apple Weather hides "0%" under every hour.
const PRECIP_SHOW_AT = 20;

// Only say what's useful: guidance appears when it applies, and a single
// quiet line confirms the all-clear otherwise.
function Advice({ coat, umbrella }: { coat: boolean; umbrella: boolean }) {
  const items: { icon: typeof Umbrella; text: string; color: string }[] = [];
  if (umbrella) items.push({ icon: Umbrella, text: "Bring an umbrella", color: "var(--system-cyan)" });
  if (coat) items.push({ icon: ThermometerSnowflake, text: "Wear a coat", color: "var(--system-blue)" });

  if (items.length === 0) {
    return (
      <div className="font-medium type-caption" style={{ fontSize: "1.7vh", color: "var(--label-secondary)" }}>
        No coat or umbrella needed
      </div>
    );
  }
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1">
      {items.map(({ icon: Icon, text, color }) => (
        <span
          key={text}
          className="inline-flex items-center gap-1.5 font-semibold type-caption"
          style={{ fontSize: "1.7vh" }}
        >
          <Icon size="1.2em" strokeWidth={2.25} style={{ color }} />
          {text}
        </span>
      ))}
    </div>
  );
}

export function Weather() {
  const { data, error, lastFetchAt } = usePolling<WeatherResponse>(api.weather, 60_000);
  const { settings } = useSettings();
  const { timezone } = settings.time;
  // "Astoria, NY" → "Astoria": the widget title is just the place. With no
  // label set, fall back the way Apple Weather does.
  const place = settings.weather.label?.split(",")[0].trim() || "My Location";

  const hourFmt = useMemo(
    () => new Intl.DateTimeFormat("en-US", { hour: "numeric", hour12: true, timeZone: timezone }),
    [timezone],
  );

  // Skip hours that have already ended (the feed can lag an hour behind), so
  // the first column can honestly read "Now".
  const nowMs = Date.now();
  const upcoming = (data?.hourly ?? [])
    .filter((h) => new Date(h.time).getTime() + 3_600_000 > nowMs)
    .slice(0, 12);
  // H/L spans the next 12 hours; the strip shows fewer so each hour breathes.
  const hourly = upcoming.slice(0, 8);
  const isNow = (time: string) => new Date(time).getTime() <= nowMs;
  const hi = upcoming.length ? Math.round(Math.max(...upcoming.map((h) => h.temp_f))) : null;
  const lo = upcoming.length ? Math.round(Math.min(...upcoming.map((h) => h.temp_f))) : null;

  return (
    <div className="material-panel flex h-full flex-col px-[2.4vh] py-[2.2vh]">
      {data ? (
        <>
          {/* Header: place + big temperature on the left, condition on the right. */}
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 font-semibold type-headline" style={{ fontSize: "2.2vh" }}>
                {place}
                <Navigation size="0.7em" fill="currentColor" strokeWidth={0} className="rotate-0" />
              </div>
              <div
                key={Math.round(data.current.temp_f)}
                className="animate-settle font-extralight tabular-nums type-display"
                style={{ fontSize: "9vh", marginLeft: "-0.04em" }}
              >
                {Math.round(data.current.temp_f)}°
              </div>
            </div>
            <div className="flex flex-col items-end pt-[0.4vh] text-right">
              <WeatherIcon icon={data.current.icon} condition={data.current.condition} size="4.4vh" />
              <div className="mt-[0.8vh] font-semibold type-headline" style={{ fontSize: "1.9vh" }}>
                {data.current.condition}
              </div>
              {hi !== null && lo !== null && (
                <div className="font-medium tabular-nums type-caption" style={{ fontSize: "1.7vh", color: "var(--label-secondary)" }}>
                  H:{hi}° L:{lo}°
                </div>
              )}
            </div>
          </div>

          <div className="mt-[1.2vh] flex items-center">
            <Advice coat={data.summary.needs_coat} umbrella={data.summary.needs_umbrella} />
            <StaleBadge lastFetchAt={lastFetchAt} staleAfterMs={180_000 /* 3× poll */} isStaleFromServer={data.stale} />
          </div>

          {/* Hourly strip: no boxes, just evenly-spaced columns under a hairline. */}
          <div className="mt-[1.8vh] border-t pt-[1.6vh]" style={{ borderColor: "var(--separator)" }}>
            <div className="grid" style={{ gridTemplateColumns: `repeat(${hourly.length || 1}, minmax(0, 1fr))` }}>
              {hourly.map((h) => (
                <div key={h.time} className="flex flex-col items-center gap-[0.7vh]">
                  <div
                    className="font-semibold type-caption"
                    style={{ fontSize: "1.35vh", color: isNow(h.time) ? "var(--label-primary)" : "var(--label-secondary)" }}
                  >
                    {isNow(h.time) ? "Now" : hourFmt.format(new Date(h.time)).replace(" ", "")}
                  </div>
                  <div className="flex h-[3.6vh] flex-col items-center justify-center">
                    <WeatherIcon condition={h.condition} time={h.time} size="2.6vh" />
                    {h.precip_prob >= PRECIP_SHOW_AT && (
                      <div className="font-semibold tabular-nums" style={{ fontSize: "1.1vh", color: "var(--system-cyan)" }}>
                        {h.precip_prob}%
                      </div>
                    )}
                  </div>
                  <div className="font-semibold tabular-nums type-headline" style={{ fontSize: "1.9vh" }}>
                    {Math.round(h.temp_f)}°
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      ) : (
        <div className="m-auto type-headline" style={{ fontSize: "1.9vh", color: "var(--label-secondary)" }}>
          {error ? "Weather unavailable" : "Loading…"}
        </div>
      )}
    </div>
  );
}
