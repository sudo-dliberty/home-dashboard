import {
  Cloud,
  CloudDrizzle,
  CloudFog,
  CloudLightning,
  CloudMoon,
  CloudRain,
  CloudSnow,
  CloudSun,
  Moon,
  Snowflake,
  Sun,
  Wind,
  type LucideIcon,
} from "lucide-react";

type IconKey =
  | "sun"
  | "moon"
  | "cloud-sun"
  | "cloud-moon"
  | "cloud"
  | "drizzle"
  | "rain"
  | "snow"
  | "thunder"
  | "fog"
  | "snowflake"
  | "wind";

const ICONS: Record<IconKey, LucideIcon> = {
  sun: Sun,
  moon: Moon,
  "cloud-sun": CloudSun,
  "cloud-moon": CloudMoon,
  cloud: Cloud,
  drizzle: CloudDrizzle,
  rain: CloudRain,
  snow: CloudSnow,
  thunder: CloudLightning,
  fog: CloudFog,
  snowflake: Snowflake,
  wind: Wind,
};

// Tailwind-friendly color tokens per icon, so the visual matches the
// weather "feel" without making it look like a kids' toy.
const COLORS: Record<IconKey, string> = {
  sun: "text-amber-300",
  moon: "text-zinc-200",
  "cloud-sun": "text-amber-200",
  "cloud-moon": "text-zinc-300",
  cloud: "text-zinc-400",
  drizzle: "text-sky-300",
  rain: "text-sky-400",
  snow: "text-sky-100",
  thunder: "text-yellow-300",
  fog: "text-zinc-300",
  snowflake: "text-sky-200",
  wind: "text-zinc-300",
};

function isNight(icon: string | undefined, time?: string): boolean {
  // NWS icon tokens end in "-day" / "-night" (set by backend _nws_icon_token).
  if (icon?.endsWith("-night")) return true;
  if (icon?.endsWith("-day")) return false;
  // Fallback: use the provided time (or local now) in NY tz.
  const d = time ? new Date(time) : new Date();
  const hourFmt = new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    hour12: false,
    timeZone: "America/New_York",
  });
  const hour = parseInt(hourFmt.format(d), 10);
  return hour < 6 || hour >= 20;
}

// Best-effort mapping that handles:
//   - NWS tokens emitted by backend _nws_icon_token (e.g. "few-clouds-day",
//     "rain-day", "tsra-night", "snow-day", "fog-day", "clear-night")
//   - Open-Meteo tokens "wmo-<code>" (mapped through the WMO code table)
//   - Free-text NWS condition like "Mostly Sunny", "Slight Chance Showers
//     And Thunderstorms" as a final fallback
export function pickIconKey(
  icon: string | undefined,
  condition: string | undefined,
  time?: string,
): IconKey {
  const night = isNight(icon, time);
  const i = (icon ?? "").toLowerCase();
  const c = (condition ?? "").toLowerCase();

  // --- NWS-style tokens ---
  if (i.startsWith("clear") || i.startsWith("skc")) return night ? "moon" : "sun";
  if (i.startsWith("few-clouds") || i.startsWith("scattered-clouds")) {
    return night ? "cloud-moon" : "cloud-sun";
  }
  if (i.startsWith("broken-clouds") || i.startsWith("overcast")) return "cloud";
  if (i.startsWith("tsra") || i.includes("thunder")) return "thunder";
  if (i.includes("snow") || i.includes("blizzard")) return "snow";
  if (i.includes("sleet") || i.includes("freezing-rain") || i.includes("ice")) return "snow";
  if (i.includes("drizzle")) return "drizzle";
  if (i.startsWith("rain") || i.includes("shower")) return "rain";
  if (i.includes("fog") || i.includes("haze") || i.includes("smoke") || i.includes("mist")) {
    return "fog";
  }
  if (i.includes("wind")) return "wind";

  // --- Open-Meteo WMO codes ---
  const m = i.match(/^wmo-(\d+)$/);
  if (m) {
    const code = parseInt(m[1], 10);
    if (code === 0) return night ? "moon" : "sun";
    if (code === 1 || code === 2) return night ? "cloud-moon" : "cloud-sun";
    if (code === 3) return "cloud";
    if (code === 45 || code === 48) return "fog";
    if (code >= 51 && code <= 57) return "drizzle";
    if (code >= 61 && code <= 67) return "rain";
    if (code >= 71 && code <= 77) return "snow";
    if (code === 85 || code === 86) return "snow";
    if (code >= 80 && code <= 82) return "rain";
    if (code >= 95) return "thunder";
  }

  // --- Free-text condition fallback ---
  if (/\bsunny\b|clear/.test(c)) return night ? "moon" : "sun";
  if (/partly|mostly\s+sunny|few/.test(c)) return night ? "cloud-moon" : "cloud-sun";
  if (/thunder/.test(c)) return "thunder";
  if (/snow|blizzard|flurr/.test(c)) return "snow";
  if (/sleet|freezing|ice/.test(c)) return "snow";
  if (/drizzle/.test(c)) return "drizzle";
  if (/rain|shower/.test(c)) return "rain";
  if (/fog|haze|mist|smoke/.test(c)) return "fog";
  if (/cloud|overcast/.test(c)) return "cloud";

  // Sensible default.
  return night ? "cloud-moon" : "cloud-sun";
}

export function WeatherIcon({
  icon,
  condition,
  time,
  size = 32,
  className = "",
}: {
  icon?: string;
  condition?: string;
  time?: string;
  size?: number | string;
  className?: string;
}) {
  const key = pickIconKey(icon, condition, time);
  const Icon = ICONS[key];
  const color = COLORS[key];
  return (
    <Icon
      size={size}
      strokeWidth={1.6}
      className={`${color} ${className}`}
      aria-label={condition}
    />
  );
}
