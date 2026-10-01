import { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Check, ChevronLeft, Search } from "lucide-react";
import { RouteBullet } from "../components/RouteBullet";
import {
  ApiError,
  geocodeZip,
  searchStations,
  type AppSettings,
  type Station,
} from "../api";
import { useSettings } from "./SettingsContext";

// Curated fallback so the timezone <select> is always useful even when
// Intl.supportedValuesOf is unavailable.
const FALLBACK_TZS = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Phoenix",
  "America/Los_Angeles",
  "America/Anchorage",
  "Pacific/Honolulu",
  "Europe/London",
  "Europe/Paris",
  "Asia/Tokyo",
];

function getTimezones(current: string): string[] {
  // Prefer the platform's full IANA list when present.
  const supported = (
    Intl as unknown as { supportedValuesOf?: (k: string) => string[] }
  ).supportedValuesOf;
  let zones = FALLBACK_TZS;
  if (typeof supported === "function") {
    try {
      zones = supported("timeZone");
    } catch {
      zones = FALLBACK_TZS;
    }
  }
  // Ensure the currently-saved zone is always selectable.
  return zones.includes(current) ? zones : [current, ...zones];
}

function closeScreen() {
  window.location.hash = "";
}

// iOS Settings–style building blocks: a small uppercase header above an
// inset, rounded group whose rows are divided by hairlines that start where
// the text starts (not at the group's edge).
function Section({
  title,
  footer,
  children,
}: {
  title: string;
  footer?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="mb-1.5 px-4 text-[13px] type-eyebrow" style={{ color: "var(--label-secondary)" }}>
        {title}
      </h2>
      <div className="overflow-hidden rounded-xl bg-[#1c1c1e] [&>*+*]:border-t [&>*+*]:border-white/10">
        {children}
      </div>
      {footer && (
        <div className="mt-1.5 px-4 text-[13px] type-caption" style={{ color: "var(--label-secondary)" }}>
          {footer}
        </div>
      )}
    </section>
  );
}

// A single row: label on the left, control on the right. Wrapped in a
// <label> so tapping anywhere on the row focuses the control.
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="ml-4 flex min-h-[44px] items-center gap-4 pr-4">
      <span className="shrink-0 text-[17px]">{label}</span>
      <div className="flex min-w-0 flex-1 justify-end">{children}</div>
    </label>
  );
}

// iOS-style switch. A real checkbox underneath keeps it accessible.
function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <span className="relative inline-flex">
      <input
        type="checkbox"
        role="switch"
        className="peer absolute inset-0 z-10 cursor-pointer opacity-0"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span
        className="h-[31px] w-[51px] rounded-full transition-colors duration-200 peer-focus-visible:ring-2 peer-focus-visible:ring-[var(--system-blue)]"
        style={{ background: checked ? "var(--system-green)" : "rgba(120,120,128,0.32)" }}
      />
      <span
        className="absolute left-[2px] top-[2px] h-[27px] w-[27px] rounded-full bg-white shadow-[0_3px_8px_rgba(0,0,0,0.15),0_3px_1px_rgba(0,0,0,0.06)] transition-transform duration-300"
        style={{
          transform: checked ? "translateX(20px)" : "translateX(0)",
          transitionTimingFunction: "var(--ease-out)",
        }}
      />
    </span>
  );
}

// Borderless, right-aligned value field — the control blends into the row.
const inputClass =
  "w-full min-w-0 bg-transparent text-right text-[17px] text-[color:var(--label-secondary)] outline-none placeholder:text-[color:var(--label-tertiary)] focus:text-white";

export function SettingsScreen() {
  const { settings, save } = useSettings();

  // Local draft state, seeded from the loaded settings. Edits stay local
  // until Save; Cancel/back discards by simply navigating away.
  const [time, setTime] = useState(settings.time);
  const [weather, setWeather] = useState(settings.weather);
  const [photos, setPhotos] = useState(settings.photos);
  const [trains, setTrains] = useState(settings.trains);

  // Re-seed the draft if settings load after this screen mounted.
  useEffect(() => {
    setTime(settings.time);
    setWeather(settings.weather);
    setPhotos(settings.photos);
    setTrains(settings.trains);
  }, [settings]);

  const timezones = useMemo(() => getTimezones(time.timezone), [time.timezone]);

  // --- ZIP → coordinates lookup (US only, key-less via /api/geocode) ---
  const [zip, setZip] = useState(settings.weather.zip ?? "");
  const [zipLooking, setZipLooking] = useState(false);
  const [zipMsg, setZipMsg] = useState<string | null>(null);
  useEffect(() => setZip(settings.weather.zip ?? ""), [settings]);

  async function lookupZip() {
    const z = zip.trim();
    setZipMsg(null);
    if (!/^\d{5}$/.test(z)) {
      setZipMsg("Enter a 5-digit US ZIP code.");
      return;
    }
    setZipLooking(true);
    try {
      const g = await geocodeZip(z);
      // The resolved lat/lon is the source of truth the backend fetches with;
      // keep the ZIP + a friendly place label alongside it.
      setWeather((w) => ({
        ...w,
        lat: g.lat,
        lon: g.lon,
        zip: g.zip,
        label: g.label || w.label,
      }));
      setZipMsg(`Found ${g.label || z} → ${g.lat.toFixed(4)}, ${g.lon.toFixed(4)}`);
    } catch {
      setZipMsg("Couldn't find that ZIP. You can enter coordinates manually below.");
    } finally {
      setZipLooking(false);
    }
  }

  // --- Station picker ---
  const [stationQuery, setStationQuery] = useState("");
  const [results, setResults] = useState<Station[]>([]);
  const [searching, setSearching] = useState(false);
  // The station whose routes drive the checkboxes. Once a station is
  // selected we keep its full record so we know its available routes.
  const [selectedStation, setSelectedStation] = useState<Station | null>(null);

  // Debounce the search ~250ms so typing doesn't hammer the backend.
  useEffect(() => {
    const q = stationQuery.trim();
    if (q.length < 2) {
      setResults([]);
      return;
    }
    setSearching(true);
    const h = setTimeout(async () => {
      try {
        setResults(await searchStations(q));
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => clearTimeout(h);
  }, [stationQuery]);

  function pickStation(s: Station) {
    setSelectedStation(s);
    setStationQuery("");
    setResults([]);
    // Keep any previously-checked routes that the new station still serves;
    // if none overlap, default to all of the station's routes.
    const kept = trains.routes.filter((r) => s.routes.includes(r));
    setTrains({
      station_stop_id: s.stop_id,
      routes: kept.length > 0 ? kept : s.routes,
    });
  }

  function toggleRoute(route: string) {
    setTrains((t) => {
      const has = t.routes.includes(route);
      return {
        ...t,
        routes: has ? t.routes.filter((r) => r !== route) : [...t.routes, route],
      };
    });
  }

  // --- Save state ---
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function validate(): string | null {
    if (!Number.isFinite(weather.lat) || weather.lat < -90 || weather.lat > 90)
      return "Latitude must be between -90 and 90.";
    if (!Number.isFinite(weather.lon) || weather.lon < -180 || weather.lon > 180)
      return "Longitude must be between -180 and 180.";
    if (!weather.user_agent.trim()) return "Weather user agent is required.";
    return null;
  }

  function formatDetail(detail: unknown): string {
    // FastAPI 422 detail is typically an array of {loc, msg}. Flatten to text.
    if (Array.isArray(detail)) {
      return detail
        .map((d) => {
          const loc = Array.isArray(d?.loc) ? d.loc.join(".") : "";
          return loc ? `${loc}: ${d?.msg ?? ""}` : String(d?.msg ?? d);
        })
        .join("; ");
    }
    if (typeof detail === "string") return detail;
    return detail ? JSON.stringify(detail) : "Request failed.";
  }

  async function onSave() {
    setErrorMsg(null);
    setSaved(false);
    const v = validate();
    if (v) {
      setErrorMsg(v);
      return;
    }
    const patch: Partial<AppSettings> = { time, weather, photos, trains };
    setSaving(true);
    try {
      await save(patch);
      setSaved(true);
      if (savedTimer.current) clearTimeout(savedTimer.current);
      savedTimer.current = setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      if (e instanceof ApiError) setErrorMsg(formatDetail(e.detail));
      else setErrorMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  // The station name shown next to the picker: the freshly-selected record,
  // or just the saved stop id when we only have that.
  const selectedStationLabel = selectedStation
    ? `${selectedStation.name} (${selectedStation.stop_id})`
    : trains.station_stop_id || "none";

  // Routes available to check: the selected station's, falling back to the
  // routes already saved so the box isn't empty before a search.
  const availableRoutes = selectedStation?.routes ?? trains.routes;

  return (
    <div className="h-screen w-full overflow-y-auto bg-black text-white">
      {/* Translucent nav bar; content scrolls underneath it. */}
      <header className="material-control sticky top-0 z-20 !shadow-none">
        <div className="mx-auto grid max-w-2xl grid-cols-3 items-center px-4 py-3">
          <button
            type="button"
            onClick={closeScreen}
            aria-label="Back to dashboard"
            className="pressable flex items-center justify-self-start text-[17px]"
            style={{ color: "var(--system-blue)" }}
          >
            <ChevronLeft size={26} strokeWidth={2.25} className="-ml-2" />
            Dashboard
          </button>
          <h1 className="justify-self-center text-[17px] font-semibold type-headline">Settings</h1>
          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            className="pressable justify-self-end text-[17px] font-semibold disabled:opacity-40"
            style={{ color: "var(--system-blue)" }}
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </header>

      <div className="mx-auto max-w-2xl px-4 pb-16 pt-6">
        <h1 className="mb-6 px-1 text-[34px] font-bold type-title">Settings</h1>

        {/* Save feedback: status inline, at the top where the eye already is. */}
        {(saved || errorMsg) && (
          <div
            className="mb-6 flex animate-settle items-center gap-2 rounded-xl px-4 py-3 text-[15px]"
            style={{
              background: errorMsg ? "rgba(255,69,58,0.15)" : "rgba(48,209,88,0.15)",
              color: errorMsg ? "var(--system-red)" : "var(--system-green)",
            }}
          >
            {errorMsg ? <AlertCircle size={18} /> : <Check size={18} strokeWidth={2.5} />}
            {errorMsg ?? "Saved"}
          </div>
        )}

        <div className="space-y-8">
          {/* TIME */}
          <Section title="Time">
            <Field label="Time Zone">
              <select
                className={`${inputClass} cursor-pointer appearance-none`}
                style={{ textAlignLast: "right" }}
                value={time.timezone}
                onChange={(e) => setTime({ ...time, timezone: e.target.value })}
              >
                {timezones.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="24-Hour Time">
              <Toggle checked={time.clock_24h} onChange={(v) => setTime({ ...time, clock_24h: v })} />
            </Field>
          </Section>

          {/* WEATHER */}
          <Section
            title="Weather"
            footer={zipMsg ?? "Enter a US ZIP code to fill in the coordinates automatically."}
          >
            <Field label="ZIP Code">
              <input
                type="text"
                inputMode="numeric"
                className={inputClass}
                placeholder="11106"
                value={zip}
                onChange={(e) => setZip(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    lookupZip();
                  }
                }}
              />
              <button
                type="button"
                onClick={lookupZip}
                disabled={zipLooking}
                className="pressable ml-3 shrink-0 text-[17px] disabled:opacity-40"
                style={{ color: "var(--system-blue)" }}
              >
                {zipLooking ? "Looking…" : "Look Up"}
              </button>
            </Field>
            <Field label="Latitude">
              <input
                type="number"
                step="any"
                className={inputClass}
                value={weather.lat}
                onChange={(e) => setWeather({ ...weather, lat: parseFloat(e.target.value) })}
              />
            </Field>
            <Field label="Longitude">
              <input
                type="number"
                step="any"
                className={inputClass}
                value={weather.lon}
                onChange={(e) => setWeather({ ...weather, lon: parseFloat(e.target.value) })}
              />
            </Field>
            <Field label="Label">
              <input
                type="text"
                className={inputClass}
                placeholder="Optional"
                value={weather.label ?? ""}
                onChange={(e) => setWeather({ ...weather, label: e.target.value })}
              />
            </Field>
            <Field label="User Agent">
              <input
                type="text"
                className={inputClass}
                value={weather.user_agent}
                onChange={(e) => setWeather({ ...weather, user_agent: e.target.value })}
              />
            </Field>
          </Section>

          {/* PHOTOS */}
          <Section title="Photos" footer="An absolute path to a folder of images on this device.">
            <Field label="Folder">
              <input
                type="text"
                className={inputClass}
                placeholder="/path/to/pictures"
                value={photos.directory}
                onChange={(e) => setPhotos({ directory: e.target.value })}
              />
            </Field>
          </Section>

          {/* SUBWAY */}
          <Section title="Subway">
            <label className="ml-4 flex min-h-[44px] items-center gap-2 pr-4">
              <Search size={17} style={{ color: "var(--label-tertiary)" }} />
              <input
                type="text"
                className="w-full bg-transparent text-[17px] outline-none placeholder:text-[color:var(--label-tertiary)]"
                placeholder="Search stations"
                value={stationQuery}
                onChange={(e) => setStationQuery(e.target.value)}
              />
              {searching && (
                <span className="shrink-0 text-[15px]" style={{ color: "var(--label-tertiary)" }}>
                  Searching…
                </span>
              )}
            </label>

            {results.length > 0 && (
              <ul className="max-h-72 overflow-y-auto [&>li+li]:border-t [&>li+li]:border-white/10">
                {results.map((s) => (
                  <li key={s.stop_id} className="ml-4">
                    <button
                      type="button"
                      onClick={() => pickStation(s)}
                      className="flex w-full items-center gap-3 py-2.5 pr-4 text-left active:bg-white/5"
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[17px]">{s.name}</span>
                        <span className="block text-[13px]" style={{ color: "var(--label-secondary)" }}>
                          {s.borough} · {s.stop_id}
                        </span>
                      </span>
                      <span className="flex shrink-0 gap-1">
                        {s.routes.map((r) => (
                          <RouteBullet key={r} route={r} size="22px" />
                        ))}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <div className="ml-4 flex min-h-[44px] items-center justify-between gap-4 pr-4">
              <span className="text-[17px]">Station</span>
              <span className="truncate text-[17px]" style={{ color: "var(--label-secondary)" }}>
                {selectedStationLabel}
              </span>
            </div>
          </Section>

          <Section title="Lines" footer="Tap a line to show or hide it on the dashboard.">
            <div className="flex flex-wrap gap-3 p-4">
              {availableRoutes.length === 0 ? (
                <span className="text-[15px]" style={{ color: "var(--label-secondary)" }}>
                  Pick a station to choose lines.
                </span>
              ) : (
                availableRoutes.map((r) => {
                  const on = trains.routes.includes(r);
                  return (
                    <button
                      key={r}
                      type="button"
                      role="switch"
                      aria-checked={on}
                      aria-label={`${r} train`}
                      onClick={() => toggleRoute(r)}
                      className="pressable relative rounded-full"
                      style={{ opacity: on ? 1 : 0.3, filter: on ? "none" : "grayscale(1)" }}
                    >
                      <RouteBullet route={r} size="44px" />
                      {on && (
                        <span
                          className="absolute -bottom-0.5 -right-0.5 grid h-[18px] w-[18px] place-items-center rounded-full ring-2 ring-[#1c1c1e]"
                          style={{ background: "var(--system-blue)" }}
                        >
                          <Check size={11} strokeWidth={3.5} />
                        </span>
                      )}
                    </button>
                  );
                })
              )}
            </div>
          </Section>
        </div>
      </div>
    </div>
  );
}
