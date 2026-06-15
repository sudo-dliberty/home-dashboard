import { useEffect, useMemo, useState } from "react";
import { useSettings } from "../settings/SettingsContext";

export function Clock() {
  const { settings } = useSettings();
  const { timezone, clock_24h } = settings.time;

  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  // Rebuild the formatters whenever the timezone or 12h/24h preference
  // changes so the kiosk reacts live to settings edits.
  const timeFmt = useMemo(
    () =>
      new Intl.DateTimeFormat("en-US", {
        hour: "numeric",
        minute: "2-digit",
        hour12: !clock_24h,
        timeZone: timezone,
      }),
    [timezone, clock_24h],
  );
  const dateFmt = useMemo(
    () =>
      new Intl.DateTimeFormat("en-US", {
        weekday: "long",
        month: "long",
        day: "numeric",
        timeZone: timezone,
      }),
    [timezone],
  );

  // Render the H:MM (AM/PM) with the colon as its own animated element so it
  // can blink at 1 Hz like a classic digital clock without re-flowing the
  // surrounding tabular-nums digits. The colon trick applies in both 12h
  // and 24h modes (hour12:false still uses ":" as the separator).
  const parts = timeFmt.formatToParts(now);

  return (
    <div className="flex flex-col justify-center px-5 py-2 leading-none">
      <div
        className="self-start font-light tabular-nums tracking-tight"
        style={{ fontSize: "min(11vh, 11vw)" }}
      >
        {parts.map((p, i) =>
          p.type === "literal" && p.value === ":" ? (
            <span key={i} className="animate-blink">
              {p.value}
            </span>
          ) : (
            <span key={i}>{p.value}</span>
          ),
        )}
      </div>
      <div className="mt-2 self-end text-zinc-300" style={{ fontSize: "min(2.4vh, 2.4vw)" }}>
        {dateFmt.format(now)}
      </div>
    </div>
  );
}
