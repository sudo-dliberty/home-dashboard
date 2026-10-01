import { useEffect, useMemo, useState } from "react";
import { useSettings } from "../settings/SettingsContext";

// Lock Screen–style clock in the same glass card as the other panels. Date
// above in a quieter weight, big tightly-tracked time below.
// No blinking colon and no AM/PM — at a glance in your own hallway, morning
// vs. evening is obvious, and a still clock is a calmer clock.
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

  const time = timeFmt
    .formatToParts(now)
    .filter((p) => p.type !== "dayPeriod")
    .map((p) => p.value)
    .join("")
    .trim();

  return (
    <div className="material-panel flex flex-col items-center px-[2.4vh] pb-[1.6vh] pt-[2vh] text-center">
      <div
        className="font-semibold type-headline"
        style={{ fontSize: "2.6vh", color: "rgba(255,255,255,0.82)" }}
      >
        {dateFmt.format(now)}
      </div>
      <div
        className="font-semibold tabular-nums type-display"
        style={{ fontSize: "min(13vh, 8vw)", color: "rgba(255,255,255,0.96)" }}
      >
        {time}
      </div>
    </div>
  );
}
