import Link from "next/link";

// S13 — 404 variant.
export default function NotFound() {
  return (
    <main className="grid min-h-screen place-items-center p-page">
      <div className="text-center">
        <p className="font-heading text-4xl font-semibold text-muted">404</p>
        <p className="mt-2 text-sm text-ink">This page doesn&apos;t exist.</p>
        <Link
          href="/dashboard"
          className="mt-4 inline-block rounded bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:bg-primary-hover"
        >
          Go to dashboard
        </Link>
      </div>
    </main>
  );
}
