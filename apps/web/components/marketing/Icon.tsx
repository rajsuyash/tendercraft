/**
 * Inline SVG icons for the landing page.
 *
 * The Stitch export loaded Material Symbols as a webfont from Google. Inlining the dozen
 * glyphs the page actually uses removes a render-blocking third-party request, removes the
 * icon-shaped layout shift while that font loads, and keeps the page working with no external
 * network at all — which matters because this is the first thing a government buyer sees.
 *
 * Paths are 24×24, stroke-based, sized by the `size` prop and coloured by `currentColor`.
 */

type IconName =
  | "spark" | "play" | "document" | "insights" | "shield" | "edit" | "review" | "send"
  | "alert" | "timer" | "hidden" | "chart" | "rule" | "draw" | "cloud" | "lock"
  | "chip" | "train" | "bolt" | "health" | "build" | "check" | "arrow" | "verified" | "heart";

const PATHS: Record<IconName, string> = {
  spark: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z",
  play: "M12 21a9 9 0 100-18 9 9 0 000 18zM10 8.5l6 3.5-6 3.5v-7z",
  document: "M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5zM14 3v5h5M9 13h6M9 17h4",
  insights: "M4 19V9M10 19V5M16 19v-6M22 19H2",
  shield: "M12 3l7 3v5c0 4.4-3 8.3-7 10-4-1.7-7-5.6-7-10V6l7-3z M9.5 11.5l1.8 1.8 3.4-3.6",
  edit: "M4 20h4l10-10a2.8 2.8 0 10-4-4L4 16v4z M13 6l4 4",
  review: "M4 5h16v11H8l-4 4V5z M9 10h6M9 13h3",
  send: "M3 11l17-7-7 17-2.5-7.5L3 11z",
  alert: "M12 3l9 16H3l9-16z M12 9v4 M12 16.5v.01",
  timer: "M12 21a8 8 0 100-16 8 8 0 000 16z M12 9v4l2.5 2 M9 2h6",
  hidden: "M3 3l18 18 M10.6 6.2A9.9 9.9 0 0112 6c5 0 9 4.5 9 6 0 .8-1 2.4-2.7 3.8"
    + " M6.5 8.2C4.4 9.6 3 11.4 3 12c0 1.5 4 6 9 6 1.3 0 2.5-.3 3.6-.8",
  chart: "M5 19V10M10 19V5M15 19v-7M20 19h-16",
  rule: "M4 7h9M4 12h9M4 17h6 M16 15l2 2 4-4",
  draw: "M4 20h4L19 9a2.8 2.8 0 10-4-4L4 16v4z M14 7l3 3",
  cloud: "M7 18a4 4 0 010-8 5.5 5.5 0 0110.5 1.5A3.5 3.5 0 0117 18H7z",
  lock: "M6 11h12v9H6v-9z M9 11V8a3 3 0 016 0v3",
  chip: "M7 7h10v10H7V7z M4 10h3M4 14h3M17 10h3M17 14h3M10 4v3M14 4v3M10 17v3M14 17v3",
  train: "M7 4h10a2 2 0 012 2v8a2 2 0 01-2 2H7a2 2 0 01-2-2V6a2 2 0 012-2z"
    + " M5 10h14 M8 20l-2 2M16 20l2 2 M9.5 13.5v.01M14.5 13.5v.01",
  bolt: "M13 3L5 14h6l-1 7 8-11h-6l1-7z",
  health: "M12 5v14M5 12h14",
  build: "M3 21h18 M6 21V10l6-5 6 5v11 M10 21v-5h4v5",
  check: "M12 21a9 9 0 100-18 9 9 0 000 18z M8.5 12.2l2.4 2.4 4.6-4.8",
  arrow: "M5 12h14M13 6l6 6-6 6",
  verified: "M12 3l2.2 2.1 3-.3.6 3 2.6 1.6-1.4 2.7 1.4 2.7-2.6 1.6-.6 3-3-.3L12 21"
    + " l-2.2-2.1-3 .3-.6-3L3.6 12.6 5 12 3.6 9.3l2.6-1.6.6-3 3 .3L12 3z M9.5 12l1.8 1.8 3.4-3.6",
  heart: "M12 20s-7-4.5-7-9a4 4 0 017-2.6A4 4 0 0119 11c0 4.5-7 9-7 9z",
};

export function Icon({
  name,
  size = 20,
  className = "",
}: {
  name: IconName;
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}

export type { IconName };
