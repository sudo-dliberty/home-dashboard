import { useEffect, useState } from "react";
import { Clock } from "./panels/Clock";
import { Photos } from "./panels/Photos";
import { Trains } from "./panels/Trains";
import { Weather } from "./panels/Weather";
import { SettingsGear } from "./components/SettingsGear";
import { SettingsProvider } from "./settings/SettingsContext";
import { SettingsScreen } from "./settings/SettingsScreen";

// Tiny hash-based route — no router library. Re-renders on hashchange.
function useHashRoute(): string {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

// Layout: photos take ~2/3 of the width on the left; right column is
// stacked Clock / Weather / Trains. All units use vh/vw so the layout
// adapts to whatever the actual Pi monitor reports (PLAN.md §1).
function Dashboard() {
  return (
    <div
      className="h-screen w-screen grid gap-2 p-2 bg-black text-white"
      style={{
        gridTemplateColumns: "minmax(0, 2fr) minmax(0, 1fr)",
        gridTemplateRows: "auto 1fr auto",
        gridTemplateAreas: `
          "photos clock"
          "photos weather"
          "photos trains"
        `,
      }}
    >
      <div style={{ gridArea: "photos" }} className="rounded-2xl overflow-hidden bg-black">
        <Photos />
      </div>
      <div style={{ gridArea: "clock" }} className="bg-zinc-950 rounded-2xl border border-zinc-700">
        <Clock />
      </div>
      <div style={{ gridArea: "weather" }}>
        <Weather />
      </div>
      <div style={{ gridArea: "trains" }}>
        <Trains />
      </div>
    </div>
  );
}

export default function App() {
  const hash = useHashRoute();
  const onSettings = hash === "#/settings";

  // The kiosk hides the cursor and clips overflow globally (see index.html) so
  // the dashboard stays clean on the Pi. The settings screen is interactive, so
  // restore a visible cursor + scrolling while it's open and revert on the way
  // back to the dashboard (setting to "" falls back to the stylesheet values).
  useEffect(() => {
    const { style } = document.body;
    style.cursor = onSettings ? "auto" : "";
    style.overflow = onSettings ? "auto" : "";
    return () => {
      style.cursor = "";
      style.overflow = "";
    };
  }, [onSettings]);

  return (
    <SettingsProvider>
      {onSettings ? (
        <SettingsScreen />
      ) : (
        <>
          <Dashboard />
          <SettingsGear />
        </>
      )}
    </SettingsProvider>
  );
}
