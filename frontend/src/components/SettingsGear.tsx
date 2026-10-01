import { useEffect, useRef, useState } from "react";
import { Settings } from "lucide-react";

// Kiosk-friendly settings affordance: invisible until the user moves the
// mouse, then materializes and auto-hides after ~3s of idle. Clicking routes
// to the hash-based settings screen.
const IDLE_MS = 3000;

export function SettingsGear() {
  const [visible, setVisible] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const show = () => {
      setVisible(true);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setVisible(false), IDLE_MS);
    };
    window.addEventListener("mousemove", show);
    return () => {
      window.removeEventListener("mousemove", show);
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  return (
    <button
      type="button"
      aria-label="Open settings"
      onClick={() => {
        window.location.hash = "#/settings";
      }}
      className={`material-control pressable fixed bottom-5 left-5 z-50 grid h-12 w-12 place-items-center rounded-full text-white/90 hover:bg-white/20 ${
        visible ? "opacity-100" : "pointer-events-none scale-90 opacity-0"
      }`}
    >
      <Settings size={24} strokeWidth={1.75} />
    </button>
  );
}
