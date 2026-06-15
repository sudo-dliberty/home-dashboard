import { useEffect, useRef, useState } from "react";
import { Settings } from "lucide-react";

// Kiosk-friendly settings affordance: invisible until the user moves the
// mouse, then fades in and auto-hides after ~3s of idle. Clicking routes to
// the hash-based settings screen.
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
      className={`fixed top-3 right-3 z-50 rounded-full bg-zinc-800/70 p-2 text-zinc-200 shadow-lg backdrop-blur transition-opacity duration-500 hover:bg-zinc-700 ${
        visible ? "opacity-70" : "pointer-events-none opacity-0"
      }`}
    >
      <Settings size={28} />
    </button>
  );
}
