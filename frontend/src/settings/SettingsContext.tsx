import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { getSettings, putSettings, type AppSettings } from "../api";

// Sensible defaults so panels (Clock/Trains) can render before the first
// /api/settings load resolves and never throw on undefined config.
export const DEFAULT_SETTINGS: AppSettings = {
  time: { timezone: "America/New_York", clock_24h: false },
  weather: {
    lat: 40.7568,
    lon: -73.9296,
    label: "Astoria",
    user_agent: "home-dashboard (local)",
  },
  photos: { directory: "" },
  trains: { station_stop_id: "R06", routes: ["N", "W"] },
};

interface SettingsContextValue {
  settings: AppSettings;
  loaded: boolean; // true once the initial GET has resolved
  reload: () => Promise<void>;
  save: (patch: Partial<AppSettings>) => Promise<AppSettings>;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [loaded, setLoaded] = useState(false);

  const reload = useCallback(async () => {
    const next = await getSettings();
    setSettings(next);
    setLoaded(true);
  }, []);

  // Load once on mount. Keep defaults on failure so the kiosk still renders.
  useEffect(() => {
    reload().catch((e) => {
      console.error("settings load failed; using defaults", e);
    });
  }, [reload]);

  // Persist then adopt the server's effective config so every panel reacts
  // live without a page reload.
  const save = useCallback(async (patch: Partial<AppSettings>) => {
    const next = await putSettings(patch);
    setSettings(next);
    setLoaded(true);
    return next;
  }, []);

  return (
    <SettingsContext.Provider value={{ settings, loaded, reload, save }}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error("useSettings must be used within <SettingsProvider>");
  return ctx;
}
