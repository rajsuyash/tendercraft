/**
 * Route-level loading skeleton for every screen under the app shell.
 *
 * Without this file Next has no loading boundary, so a navigation renders NOTHING until the
 * whole server render resolves — measured at 6.8s on /tenders/:id/readiness in prod. The
 * click looked like it had not registered. This is the boundary that makes the shell paint
 * immediately and the page stream in behind it (DESIGN_SPEC §E: skeletons, never a bare
 * spinner; the sidebar stays interactive because it lives in the layout above this).
 *
 * ponytail: one shared skeleton for all app routes. Per-screen shapes (§E specifies them
 * individually) can override by adding loading.tsx next to that page — this is the floor.
 */
function Bar({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-surface-alt ${className}`} />;
}

export default function AppLoading() {
  return (
    <div data-route-loading className="px-page py-page" aria-busy aria-label="Loading">
      <Bar className="h-7 w-72" />
      <Bar className="mt-3 h-4 w-96" />

      <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="rounded-lg border border-border bg-surface p-4">
            <Bar className="h-4 w-24" />
            <Bar className="mt-3 h-8 w-32" />
          </div>
        ))}
      </div>

      <div className="mt-6 overflow-hidden rounded-lg border border-border bg-surface">
        <div className="border-b border-border p-4">
          <Bar className="h-4 w-40" />
        </div>
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="flex items-center gap-4 border-b border-border px-4 py-3">
            <Bar className="h-4 flex-1" />
            <Bar className="h-4 w-28" />
            <Bar className="h-4 w-20" />
          </div>
        ))}
      </div>
    </div>
  );
}
