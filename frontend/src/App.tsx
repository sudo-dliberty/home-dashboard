import { useEffect, useState } from "react";
import { Clock } from "./panels/Clock";
import { Backdrop, Photos, useSlideshow } from "./panels/Photos";
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

// Layout: the current photo, blurred, fills the screen as an ambient
// backdrop. The photo itself floats in the left ~2/3; the right column holds
// translucent Clock, Weather and Trains panels. All units use vh/vw so the
// layout adapts to whatever the actual Pi monitor reports (PLAN.md §1).
function Dashboard() {
  const show = useSlideshow();
  return (
    <>
      <Backdrop show={show} />
      <div
        className="relative z-10 grid h-screen w-screen text-white"
        style={{
          padding: "3vh",
          gap: "2.4vh 3vh",
          gridTemplateColumns: "minmax(0, 2fr) minmax(0, 1fr)",
          gridTemplateRows: "auto auto minmax(0, 1fr)",
          gridTemplateAreas: `
            "photos clock"
            "photos weather"
            "photos trains"
          `,
        }}
      >
        <div style={{ gridArea: "photos" }} className="min-h-0">
          <Photos show={show} />
        </div>
        <div style={{ gridArea: "clock" }}>
          <Clock />
        </div>
        <div style={{ gridArea: "weather" }}>
          <Weather />
        </div>
        <div style={{ gridArea: "trains" }} className="min-h-0">
          <Trains />
        </div>
      </div>
    </>
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
