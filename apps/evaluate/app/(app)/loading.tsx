function Bar({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-surface-alt ${className}`} />;
}

/** Without this file a navigation renders nothing until the whole server render resolves.
 *  The bidder product shipped that way and every click looked broken. */
export default function Loading() {
  return (
    <main data-route-loading aria-busy className="mx-auto max-w-6xl px-page py-page">
      <Bar className="h-7 w-80" />
      <Bar className="mt-3 h-4 w-96" />
      <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="rounded-card border border-border bg-surface p-card">
            <Bar className="h-4 w-24" /><Bar className="mt-3 h-8 w-32" />
          </div>
        ))}
      </div>
      <div className="mt-6 rounded-card border border-border bg-surface">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="flex gap-4 border-b border-border px-card py-3 last:border-0">
            <Bar className="h-4 flex-1" /><Bar className="h-4 w-24" /><Bar className="h-4 w-20" />
          </div>
        ))}
      </div>
    </main>
  );
}
