// MTA-style colored circle with the route letter/number. Colors follow the
// official MTA line-group palette; unknown routes fall back to a neutral grey
// so any station's lines still render sensibly.
const ROUTE_BG: Record<string, string> = {
  // Broadway (BMT) yellow
  N: "#FCCC0A",
  Q: "#FCCC0A",
  R: "#FCCC0A",
  W: "#FCCC0A",
  // IRT Broadway–7th Ave red
  "1": "#EE352E",
  "2": "#EE352E",
  "3": "#EE352E",
  // Lexington Ave green
  "4": "#00933C",
  "5": "#00933C",
  "6": "#00933C",
  // Flushing purple
  "7": "#B933AD",
  // 8th Ave blue
  A: "#0039A6",
  C: "#0039A6",
  E: "#0039A6",
  // 6th Ave orange
  B: "#FF6319",
  D: "#FF6319",
  F: "#FF6319",
  M: "#FF6319",
  // Crosstown light green
  G: "#6CBE45",
  // Nassau brown
  J: "#996633",
  Z: "#996633",
  // Canarsie grey
  L: "#A7A9AC",
  // Shuttles / SIR
  S: "#808183",
  SIR: "#0078C6",
};

// Yellow/grey/light backgrounds need black text for contrast; everything
// else reads better in white.
const DARK_TEXT = new Set(["N", "Q", "R", "W", "L", "S"]);

export function RouteBullet({ route, size = "1em" }: { route: string; size?: string }) {
  const bg = ROUTE_BG[route] ?? "#6B7280"; // neutral grey fallback
  const color = DARK_TEXT.has(route) ? "#000" : "#fff";
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-full font-bold"
      style={{
        width: size,
        height: size,
        fontSize: `calc(${size} * 0.62)`,
        lineHeight: 1,
        backgroundColor: bg,
        color,
        letterSpacing: "-0.02em",
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.25), 0 2px 6px rgba(0,0,0,0.25)",
      }}
      aria-label={`${route} train`}
    >
      {route}
    </span>
  );
}
