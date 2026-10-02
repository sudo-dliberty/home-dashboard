import { useEffect, useMemo, useRef, useState } from "react";
import { api, type PhotosResponse } from "../api";
import { usePolling } from "../hooks/usePolling";

const ROTATE_MS = 60_000;
// How long the outgoing photo stays mounted during a change. Must outlast the
// fade-out/materialize/fade-slow animations so it's already invisible (or
// fully covered, for the backdrop) by the time it's removed.
const CROSSFADE_MS = 2_600;

function pickRandom<T>(arr: T[], avoid?: T): T | null {
  if (arr.length === 0) return null;
  if (arr.length === 1) return arr[0];
  for (let i = 0; i < 5; i++) {
    const c = arr[Math.floor(Math.random() * arr.length)];
    if (c !== avoid) return c;
  }
  return arr[0];
}

export interface Slideshow {
  current: string | null;
  previous: string | null;
  error: string | null;
  dirMissing: boolean;
}

// Owns slideshow state so both the foreground photo and the full-screen
// ambient backdrop show the same image. `previous` is kept so the new photo
// can cross-fade over the old one instead of flashing through black.
export function useSlideshow(): Slideshow {
  // Poll the listing infrequently so newly-dropped photos appear without restart.
  const { data, error } = usePolling<PhotosResponse>(api.photos, 5 * 60_000);
  const photos = useMemo(() => data?.photos ?? [], [data]);
  const [pair, setPair] = useState<{ current: string | null; previous: string | null }>({
    current: null,
    previous: null,
  });

  useEffect(() => {
    const advance = () =>
      setPair((p) => ({
        previous: p.current,
        current: pickRandom(photos, p.current ?? undefined),
      }));
    if (photos.length === 0) {
      setPair({ current: null, previous: null });
      return;
    }
    advance();
    const t = setInterval(advance, ROTATE_MS);
    return () => clearInterval(t);
  }, [photos]);

  useEffect(() => {
    if (!pair.previous) return;
    const t = setTimeout(() => setPair((p) => ({ ...p, previous: null })), CROSSFADE_MS);
    return () => clearTimeout(t);
  }, [pair.previous]);

  return {
    ...pair,
    error: error && !data ? error : null,
    dirMissing: data?.error === "photo_dir_missing",
  };
}

// The backdrop is drawn into a tiny canvas and stretched to fill the screen:
// the browser's smooth upscaling does the blurring for free. A CSS
// `filter: blur()` over the whole viewport looks the same on a Mac, but the
// Pi 3's GPU can't allocate a render surface that large and silently drops
// it, leaving a black screen.
const BACKDROP_W = 64;
const BACKDROP_H = 36;
// The backdrop is only ever drawn 64px wide, so fetch a tiny copy: decoding
// a full-size photo just to throw it away is slow on the Pi.
const BACKDROP_FETCH_PX = 256;

// Long edge, in device pixels, the photo can occupy: the panel is ~2/3 of
// the width and nearly the full height. Fetching about that size means the
// browser barely rescales — the Pi's GPU scaling is fast but soft.
function photoFetchPx(): number {
  const dpr = window.devicePixelRatio || 1;
  return Math.max((window.innerWidth * 2) / 3, window.innerHeight) * dpr;
}

function BlurredPhoto({ src, className }: { src: string; className: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      const ctx = ref.current?.getContext("2d");
      if (!ctx) return;
      // object-fit: cover, with a little overscan so the blur doesn't pull
      // in dark edges.
      const scale = Math.max(BACKDROP_W / img.width, BACKDROP_H / img.height) * 1.15;
      const w = img.width * scale;
      const h = img.height * scale;
      ctx.filter = "blur(2px) saturate(1.5) brightness(0.6)";
      ctx.drawImage(img, (BACKDROP_W - w) / 2, (BACKDROP_H - h) / 2, w, h);
    };
    img.src = src;
    return () => {
      img.onload = null;
    };
  }, [src]);

  return (
    <canvas
      ref={ref}
      width={BACKDROP_W}
      height={BACKDROP_H}
      className={`absolute inset-0 h-full w-full ${className}`}
    />
  );
}

// Full-viewport, heavily blurred copy of the current photo. Gives the whole
// screen the photo's color and light (like Apple TV / StandBy) so the
// translucent panels have something to pick up. It only changes once a
// minute and cross-fades slowly, so it never reads as a moving background.
export function Backdrop({ show }: { show: Slideshow }) {
  return (
    <div className="fixed inset-0 z-0 overflow-hidden bg-black" aria-hidden>
      {[show.previous, show.current].map(
        (name, i) =>
          name && (
            <BlurredPhoto
              key={name}
              src={api.photoUrl(name, BACKDROP_FETCH_PX)}
              className={i === 1 ? "animate-fade-slow" : ""}
            />
          ),
      )}
      {/* Gentle vignette keeps white text legible on bright photos. */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_30%,rgba(0,0,0,0.45)_100%)]" />
    </div>
  );
}

function Placeholder({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="material-panel flex h-full w-full items-center justify-center text-center type-headline"
      style={{ color: "var(--label-secondary)", fontSize: "2.2vh" }}
    >
      {children}
    </div>
  );
}

// One photo, fitted to the panel like object-fit: contain but sized as the
// element itself, so rounded corners and the shadow hug the picture. Unlike
// max-width/max-height, this also scales small photos *up* to fill the space.
function FittedPhoto({ src, className }: { src: string; className: string }) {
  const [ratio, setRatio] = useState<number | null>(null);
  return (
    <img
      src={src}
      alt=""
      draggable={false}
      onLoad={(e) => setRatio(e.currentTarget.naturalWidth / e.currentTarget.naturalHeight)}
      className={`col-start-1 row-start-1 rounded-[28px] ${ratio ? "" : "invisible"} ${className}`}
      style={{
        // Container units resolve against the panel (container-type: size).
        width: ratio ? `min(100cqw, ${100 * ratio}cqh)` : undefined,
        aspectRatio: ratio ?? undefined,
        boxShadow: "0 40px 80px -24px rgba(0,0,0,0.75), 0 0 0 1px rgba(255,255,255,0.06)",
      }}
    />
  );
}

export function Photos({ show }: { show: Slideshow }) {
  if (show.error) return <Placeholder>Photos unavailable</Placeholder>;
  if (show.dirMissing) return <Placeholder>Choose a photo folder in Settings</Placeholder>;
  if (!show.current) return null;

  // The photo floats over its own blurred backdrop with rounded corners and
  // a deep shadow. Both layers are stacked in one grid cell and cross-fade:
  // the outgoing photo dissolves while the incoming one materializes, so a
  // differently-shaped old photo never shows around the edges of the new one.
  return (
    <div className="grid h-full w-full grid-cols-[100%] grid-rows-[100%] place-items-center [container-type:size]">
      {[show.previous, show.current].map(
        (name, i) =>
          name && (
            <FittedPhoto
              key={name}
              src={api.photoUrl(name, photoFetchPx())}
              className={i === 1 ? "animate-materialize motion-scale" : "animate-fade-out"}
            />
          ),
      )}
    </div>
  );
}
