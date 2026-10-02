// Thin typed fetchers against the local FastAPI backend.
// Contracts mirror docs/CONTRACTS.md.

// `route` is any MTA line id now (the station can serve any of them),
// not just the old Astoria-specific N | W.
export interface TrainArrival {
  route: string;
  minutes: number;
  arrival: string; // ISO 8601
}

// One direction of arrivals plus the registry-derived human label.
export interface TrainDirection {
  label: string;
  arrivals: TrainArrival[];
}

export interface TrainsResponse {
  station: string;
  stop_id: string;
  fetched_at: string;
  feed_age_s: number;
  stale?: boolean;
  north: TrainDirection;
  south: TrainDirection;
}

// --- Settings (docs/CONTRACTS.md "Effective config" shape) ---

export interface TimeSettings {
  timezone: string; // IANA tz name
  clock_24h: boolean;
}

export interface WeatherSettings {
  lat: number;
  lon: number;
  label?: string;
  zip?: string; // optional US ZIP; resolved to lat/lon via /api/geocode
  user_agent: string;
}

// Result of GET /api/geocode?zip= — resolved coordinates + a place label.
export interface GeocodeResult {
  zip: string;
  lat: number;
  lon: number;
  label: string;
}

export interface PhotosSettings {
  directory: string;
}

export interface TrainsSettings {
  station_stop_id: string;
  routes: string[];
}

export interface AppSettings {
  time: TimeSettings;
  weather: WeatherSettings;
  photos: PhotosSettings;
  trains: TrainsSettings;
}

// Station registry record from GET /api/stations.
export interface Station {
  stop_id: string;
  name: string;
  borough: string;
  routes: string[];
  north_label: string;
  south_label: string;
}

export interface WeatherHour {
  time: string;
  temp_f: number;
  precip_prob: number;
  condition: string;
}

export interface WeatherResponse {
  fetched_at: string;
  provider: "nws" | "open-meteo";
  stale?: boolean;
  current: {
    temp_f: number;
    feels_like_f?: number;
    condition: string;
    icon: string;
    precip_prob: number;
  };
  hourly: WeatherHour[];
  summary: {
    needs_coat: boolean;
    needs_umbrella: boolean;
    min_temp_next_12h_f: number;
    max_precip_prob_next_12h: number;
  };
}

export interface PhotosResponse {
  photos: string[];
  error?: string;
}

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path} → HTTP ${r.status}`);
  return (await r.json()) as T;
}

// Raised when PUT /api/settings rejects input. Carries the parsed `detail`
// so the settings UI can surface the backend's per-field 422 message.
export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function getSettings(): Promise<AppSettings> {
  return getJson<AppSettings>("/api/settings");
}

export async function putSettings(patch: Partial<AppSettings>): Promise<AppSettings> {
  const r = await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify(patch),
  });
  if (!r.ok) {
    let detail: unknown = null;
    try {
      const body = await r.json();
      detail = body?.detail ?? body;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(r.status, detail, `PUT /api/settings → HTTP ${r.status}`);
  }
  return (await r.json()) as AppSettings;
}

export function searchStations(q: string): Promise<Station[]> {
  return getJson<Station[]>(`/api/stations?q=${encodeURIComponent(q)}`);
}

// Resolve a US ZIP to coordinates. Throws (HTTP 400/404) on a bad/unknown ZIP
// so the settings UI can show a "couldn't find that ZIP" hint.
export function geocodeZip(zip: string): Promise<GeocodeResult> {
  return getJson<GeocodeResult>(`/api/geocode?zip=${encodeURIComponent(zip)}`);
}

export const api = {
  trains: () => getJson<TrainsResponse>("/api/trains"),
  weather: () => getJson<WeatherResponse>("/api/weather"),
  photos: () => getJson<PhotosResponse>("/api/photos"),
  // `max` asks the server for a copy no larger than that many pixels on its
  // long edge, so the browser draws it at (nearly) 1:1.
  photoUrl: (filename: string, max?: number) =>
    `/api/photos/${encodeURIComponent(filename)}${max ? `?max=${Math.round(max)}` : ""}`,
};
