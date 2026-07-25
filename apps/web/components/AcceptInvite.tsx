"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function AcceptInvite({ token }: { token: string }) {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");
  const [error, setError] = useState<string | null>(null);

  async function accept() {
    setState("busy");
    setError(null);
    const res = await fetch("/api/invitations/accept", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ token }),
    });
    const body = await res.json();
    if (!body.ok) {
      setError(body.error?.message ?? "Could not accept this invitation");
      setState("idle");
      return;
    }
    setState("done");
    router.push("/dashboard");
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center p-page">
      <div className="rounded-card border border-border bg-surface p-card">
        <h1 className="font-heading text-xl font-medium text-ink">Join workspace</h1>
        <p className="mt-2 text-sm text-muted">
          You have been invited to a TenderCraft workspace. Accepting links this invitation
          to the account you are signed in as — it must match the address it was sent to.
        </p>
        {error ? (
          <p data-invite-error className="mt-3 rounded border border-danger bg-danger-bg p-2 text-sm text-danger">
            {error}
          </p>
        ) : null}
        <button
          type="button"
          data-accept-invite
          onClick={accept}
          disabled={state !== "idle"}
          className="mt-4 w-full rounded bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {state === "busy" ? "Joining…" : state === "done" ? "Joined" : "Accept invitation"}
        </button>
        <p className="mt-3 text-center text-xs text-muted">
          Not signed in?{" "}
          <a href="/login" className="text-primary underline">
            Sign in first
          </a>
          , then reopen this link.
        </p>
      </div>
    </main>
  );
}
