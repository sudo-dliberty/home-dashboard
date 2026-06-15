import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft } from "lucide-react";
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

// Small framed section matching the dashboard panels.
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-zinc-700 bg-zinc-950 p-5">
      <h2 className="mb-4 text-lg font-semibold text-zinc-100">{title}</h2>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm text-zinc-400">{label}</span>
      {children}
    </label>
  );
}

const inputClass =
  "w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-zinc-100 outline-none focus:border-zinc-500";

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
    <div className="h-screen w-full overflow-y-auto bg-black text-zinc-100">
      <div className="mx-auto max-w-3xl px-6 py-8">
        <header className="mb-6 flex items-center gap-3">
          <button
            type="button"
            onClick={closeScreen}
            aria-label="Back to dashboard"
            className="flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm hover:bg-zinc-800"
          >
            <ArrowLeft size={18} /> Back
          </button>
          <h1 className="text-2xl font-semibold">Settings</h1>
        </header>

        <div className="space-y-5">
          {/* TIME */}
          <Section title="Time">
            <Field label="Timezone">
              <select
                className={inputClass}
                value={time.timezone}
                onChange={(e) => setTime({ ...time, timezone: e.target.value })}
              >
                {timezones.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
            </Field>
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={time.clock_24h}
                onChange={(e) => setTime({ ...time, clock_24h: e.target.checked })}
              />
              <span className="text-sm text-zinc-300">Use 24-hour clock</span>
            </label>
          </Section>

          {/* WEATHER */}
          <Section title="Weather">
            <Field label="ZIP code (US — fills in coordinates)">
              <div className="flex gap-2">
                <input
                  type="text"
                  inputMode="numeric"
                  className={inputClass}
                  placeholder="e.g. 11106"
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
                  className="shrink-0 rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm hover:bg-zinc-800 disabled:opacity-50"
                >
                  {zipLooking ? "Looking…" : "Look up"}
                </button>
              </div>
            </Field>
            {zipMsg && <div className="text-sm text-zinc-400">{zipMsg}</div>}

            <div className="grid grid-cols-2 gap-4">
              <Field label="Latitude (auto-filled from ZIP)">
                <input
                  type="number"
                  step="any"
                  className={inputClass}
                  value={weather.lat}
                  onChange={(e) =>
                    setWeather({ ...weather, lat: parseFloat(e.target.value) })
                  }
                />
              </Field>
              <Field label="Longitude (auto-filled from ZIP)">
                <input
                  type="number"
                  step="any"
                  className={inputClass}
                  value={weather.lon}
                  onChange={(e) =>
                    setWeather({ ...weather, lon: parseFloat(e.target.value) })
                  }
                />
              </Field>
            </div>
            <Field label="Label (optional)">
              <input
                type="text"
                className={inputClass}
                value={weather.label ?? ""}
                onChange={(e) => setWeather({ ...weather, label: e.target.value })}
              />
            </Field>
            <Field label="User agent">
              <input
                type="text"
                className={inputClass}
                value={weather.user_agent}
                onChange={(e) =>
                  setWeather({ ...weather, user_agent: e.target.value })
                }
              />
            </Field>
          </Section>

          {/* PHOTOS */}
          <Section title="Photos">
            <Field label="Directory (absolute path)">
              <input
                type="text"
                className={inputClass}
                placeholder="/absolute/path/to/pictures"
                value={photos.directory}
                onChange={(e) => setPhotos({ directory: e.target.value })}
              />
            </Field>
          </Section>

          {/* SUBWAY */}
          <Section title="Subway">
            <Field label="Station">
              <input
                type="text"
                className={inputClass}
                placeholder="Search station name…"
                value={stationQuery}
                onChange={(e) => setStationQuery(e.target.value)}
              />
            </Field>

            {searching && <div className="text-sm text-zinc-500">Searching…</div>}
            {results.length > 0 && (
              <ul className="max-h-60 overflow-y-auto rounded-lg border border-zinc-700">
                {results.map((s) => (
                  <li key={s.stop_id}>
                    <button
                      type="button"
                      onClick={() => pickStation(s)}
                      className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-zinc-800"
                    >
                      <span>
                        {s.name}{" "}
                        <span className="text-zinc-500">
                          ({s.borough}) · {s.routes.join(" ")}
                        </span>
                      </span>
                      <span className="text-xs text-zinc-600">{s.stop_id}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <div className="text-sm text-zinc-300">
              Selected:{" "}
              <span className="font-medium text-zinc-100">{selectedStationLabel}</span>
            </div>

            <div>
              <div className="mb-2 text-sm text-zinc-400">Routes</div>
              {availableRoutes.length === 0 ? (
                <div className="text-sm text-zinc-500">
                  Pick a station to choose routes.
                </div>
              ) : (
                <div className="flex flex-wrap gap-3">
                  {availableRoutes.map((r) => (
                    <label
                      key={r}
                      className="flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5"
                    >
                      <input
                        type="checkbox"
                        className="h-4 w-4"
                        checked={trains.routes.includes(r)}
                        onChange={() => toggleRoute(r)}
                      />
                      <span className="font-semibold">{r}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          </Section>

          {/* SAVE BAR */}
          <div className="flex items-center gap-3 pb-10">
            <button
              type="button"
              onClick={onSave}
              disabled={saving}
              className="rounded-xl bg-zinc-100 px-5 py-2 font-semibold text-black hover:bg-white disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              onClick={closeScreen}
              className="rounded-xl border border-zinc-700 bg-zinc-900 px-5 py-2 hover:bg-zinc-800"
            >
              Cancel
            </button>
            {saved && <span className="text-sm text-emerald-400">Saved ✓</span>}
            {errorMsg && <span className="text-sm text-red-400">{errorMsg}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
