"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const { error } = await createClient().auth.signInWithPassword({ email, password });
    if (error) {
      setError("Incorrect email or password.");
      setLoading(false);
      return;
    }
    router.push("/evaluations");
    router.refresh();
  }

  return (
    <main className="grid min-h-screen grid-cols-1 md:grid-cols-[45fr_55fr]">
      <section className="hidden flex-col justify-between bg-primary p-10 text-on-primary md:flex">
        <span className="font-heading text-xl font-semibold">TenderCraft Evaluate</span>
        <div>
          <p className="font-heading text-lg leading-snug">
            Defensible tender evaluation. The statutory sequence, enforced in code.
          </p>
          <ul className="mt-6 space-y-2 text-sm text-on-primary/80">
            <li>Financial bids stay sealed until technical scores are locked</li>
            <li>Every mark traces to a named evaluator and a cited page</li>
            <li>Append-only audit trail for CVC / CAG scrutiny</li>
          </ul>
        </div>
        <span className="text-xs text-on-primary/60">
          Independent of any bidder-assistance product. Separate database, no shared data.
        </span>
      </section>

      <section className="flex items-center justify-center bg-surface px-6 py-12">
        <form onSubmit={onSubmit} className="w-full max-w-sm">
          <h1 className="font-heading text-2xl font-semibold text-ink">Sign in</h1>
          <p className="mt-1 text-sm text-muted">Evaluation workspace for public authorities.</p>

          <label className="mt-7 block text-sm font-medium text-ink">
            Email
            <input
              type="email" required autoComplete="email" value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-3.5 text-sm text-ink outline-none focus:border-primary focus:bg-surface"
            />
          </label>
          <label className="mt-4 block text-sm font-medium text-ink">
            Password
            <input
              type="password" required autoComplete="current-password" value={password}
              aria-invalid={error ? true : undefined}
              onChange={(e) => setPassword(e.target.value)}
              className={`mt-1.5 block min-h-11 w-full rounded border bg-surface-alt px-3.5 text-sm text-ink outline-none focus:bg-surface ${
                error ? "border-danger" : "border-border focus:border-primary"
              }`}
            />
          </label>
          {error && (
            <p data-auth-error role="alert" className="mt-2 text-sm text-danger">{error}</p>
          )}
          <button
            type="submit" disabled={loading}
            className="mt-7 flex min-h-11 w-full items-center justify-center rounded bg-primary text-sm font-semibold text-on-primary shadow-sm hover:bg-primary-hover disabled:opacity-60"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}
