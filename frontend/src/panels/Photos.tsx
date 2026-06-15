import { useEffect, useMemo, useState } from "react";
import { api, type PhotosResponse } from "../api";
import { usePolling } from "../hooks/usePolling";

const ROTATE_MS = 60_000;

function pickRandom<T>(arr: T[], avoid?: T): T | null {
  if (arr.length === 0) return null;
  if (arr.length === 1) return arr[0];
  for (let i = 0; i < 5; i++) {
    const c = arr[Math.floor(Math.random() * arr.length)];
    if (c !== avoid) return c;
  }
  return arr[0];
}

export function Photos() {
  // Poll the listing infrequently so newly-dropped photos appear without restart.
  const { data, error } = usePolling<PhotosResponse>(api.photos, 5 * 60_000);
  const photos = useMemo(() => data?.photos ?? [], [data]);
  const [current, setCurrent] = useState<string | null>(null);

  useEffect(() => {
    if (photos.length === 0) {
      setCurrent(null);
      return;
    }
    setCurrent((prev) => pickRandom(photos, prev ?? undefined));
    const t = setInterval(() => {
      setCurrent((prev) => pickRandom(photos, prev ?? undefined));
    }, ROTATE_MS);
    return () => clearInterval(t);
  }, [photos]);

  if (error && !data) {
    return (
      <div className="h-full flex items-center justify-center bg-black text-red-400">
        Photos unavailable
      </div>
    );
  }
  if (data?.error === "photo_dir_missing") {
    return (
      <div className="h-full flex items-center justify-center bg-black text-zinc-500">
        Set PHOTO_DIR to enable photos
      </div>
    );
  }
  if (!current) {
    return <div className="h-full bg-black" />;
  }
  return (
    <div className="h-full w-full bg-black flex items-center justify-center overflow-hidden">
      <img
        key={current}
        src={api.photoUrl(current)}
        alt=""
        className="max-h-full max-w-full object-contain animate-fade"
        draggable={false}
      />
    </div>
  );
}
