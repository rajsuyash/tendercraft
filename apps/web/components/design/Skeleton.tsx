/** Loading skeleton — the design contract requires skeletons, never bare spinners. */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div data-skeleton className={`animate-pulse rounded bg-border/60 ${className}`} />;
}
