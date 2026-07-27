/** Pulled from the landing page's own language so the film and the site are one brand. */
export const T = {
  bg: "#faf8ff",
  surface: "#ffffff",
  ink: "#131b2e",
  inkSoft: "#434654",
  hairline: "#e6e8f5",
  primary: "#0052cc",
  primaryDeep: "#003d9b",
  accent: "#ff9933",
  inverse: "#101728",
  onInverse: "#eef0ff",
  display: "Geist, Inter, -apple-system, system-ui, sans-serif",
  mono: "'JetBrains Mono', ui-monospace, monospace",
} as const;

export const FPS = 30;

/**
 * Scene boundaries in SECONDS, taken from ffmpeg silencedetect on the actual voiceover rather
 * than guessed. Each cut lands in a real pause between paragraphs, so the picture never
 * changes mid-sentence.
 */
export const SCENES = [
  { id: "problem", from: 0.0, to: 8.1 },
  { id: "extract", from: 8.1, to: 24.1 },
  { id: "denominator", from: 24.1, to: 31.8 },
  { id: "matrix", from: 31.8, to: 42.0 },
  { id: "cite", from: 42.0, to: 51.1 },
  { id: "close", from: 51.1, to: 55.4 },
] as const;

export const sec = (s: number) => Math.round(s * FPS);
export const dur = (i: number) => sec(SCENES[i]!.to) - sec(SCENES[i]!.from);
