"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createClient } from "@/lib/supabase/client";

// S1 — Sign in. Split layout: brand panel + form. Auth failure renders inline
// [data-auth-error] (S1-D1), never a toast-only error.
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
    const supabase = createClient();
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) {
      setError("Incorrect email or password.");
      setLoading(false);
      return;
    }
    router.push("/dashboard");
    router.refresh();
  }

  return (
    <main className="grid min-h-screen grid-cols-1 md:grid-cols-[45fr_55fr]">
      <section className="hidden flex-col justify-between bg-primary p-10 text-on-primary md:flex">
        <span className="font-heading text-2xl font-semibold">TenderCraft</span>
        <div>
          <p className="font-heading text-xl leading-snug">
            From tender PDF to evaluator-ready proposal. Cited, compliant, human-approved.
          </p>
          <ul className="mt-6 space-y-2 text-sm text-on-primary/80">
            <li>Every claim cited to your documents</li>
            <li>Deterministic compliance gates</li>
            <li>Data stays in India</li>
          </ul>
        </div>
        <span className="text-xs text-on-primary/60">Outputs are decision support, not legal advice.</span>
      </section>

      <section className="flex items-center justify-center bg-surface px-6 py-12">
        <form onSubmit={onSubmit} className="w-full max-w-sm">
          <h1 className="font-heading text-2xl font-semibold text-ink">Sign in to your workspace</h1>
          <label className="mt-6 block text-sm font-medium text-ink">
            Email
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded border border-border px-3 py-2 text-sm outline-none focus:border-primary"
            />
          </label>
          <label className="mt-4 block text-sm font-medium text-ink">
            Password
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={`mt-1 w-full rounded border px-3 py-2 text-sm outline-none focus:border-primary ${
                error ? "border-danger" : "border-border"
              }`}
            />
          </label>
          {error && (
            <p data-auth-error className="mt-2 text-sm text-danger">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="mt-6 w-full rounded bg-primary py-2 text-sm font-medium text-on-primary hover:bg-primary-hover disabled:opacity-60"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
          <p className="mt-4 text-center text-sm text-muted">
            New here? Start free — 3 analyses/month
          </p>
        </form>
      </section>
    </main>
  );
}
