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
          {/* Large title, then the form — the iOS sign-in shape. */}
          <h1 className="font-heading text-2xl font-semibold text-ink">Sign in to your workspace</h1>

          {/* iOS text fields are FILLED rather than outlined: a tinted well with a hairline,
              and 44px tall so the control is a comfortable target. */}
          <label className="mt-7 block text-sm font-medium text-ink">
            Email
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1.5 block min-h-11 w-full rounded border border-border bg-surface-alt px-3.5 text-sm text-ink outline-none placeholder:text-muted focus:border-primary focus:bg-surface"
            />
          </label>

          <label className="mt-4 block text-sm font-medium text-ink">
            Password
            <input
              type="password"
              required
              autoComplete="current-password"
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? "auth-error" : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={`mt-1.5 block min-h-11 w-full rounded border bg-surface-alt px-3.5 text-sm text-ink outline-none focus:bg-surface ${
                error ? "border-danger" : "border-border focus:border-primary"
              }`}
            />
          </label>

          {error && (
            <p id="auth-error" data-auth-error role="alert" className="mt-2 text-sm text-danger">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="mt-7 flex min-h-11 w-full items-center justify-center rounded bg-primary text-sm font-semibold text-on-primary shadow-sm hover:bg-primary-hover disabled:opacity-60"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>

          <p className="mt-5 text-center text-sm text-muted">
            New here? Start free — 3 analyses/month
          </p>
        </form>
      </section>
    </main>
  );
}
