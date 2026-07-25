"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export type Member = {
  user_id: string;
  role: string;
  email: string | null;
  full_name: string | null;
  created_at: string | null;
};

export type Invitation = {
  id: string;
  email: string;
  role: string;
  expires_at: string;
};

const ROLES = [
  "viewer",
  "writer",
  "reviewer",
  "compliance_checker",
  "legal",
  "approver",
  "admin",
] as const;

const ROLE_CHIP: Record<string, string> = {
  viewer: "bg-surface-alt text-muted",
  writer: "bg-surface-alt text-ink",
  reviewer: "bg-primary/10 text-primary",
  compliance_checker: "bg-warning-bg text-warning",
  legal: "bg-warning-bg text-warning",
  approver: "bg-success-bg text-success",
  admin: "bg-primary text-white",
};

const label = (r: string) => r.replace(/_/g, " ");

export function MembersPanel({
  workspaceId,
  members,
  invitations,
  canManage,
  currentUserId,
}: {
  workspaceId: string;
  members: Member[];
  invitations: Invitation[];
  canManage: boolean;
  currentUserId: string;
}) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<string>("writer");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [link, setLink] = useState<string | null>(null);

  async function call(path: string, init: RequestInit) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(path, init);
      const body = await res.json();
      if (!body.ok) {
        setError(body.error?.message ?? "Request failed");
        return null;
      }
      router.refresh();
      return body.data;
    } finally {
      setBusy(false);
    }
  }

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    setLink(null);
    const data = await call(`/api/workspaces/${workspaceId}/invitations`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email, role }),
    });
    if (data?.token) {
      // Shown once — the engine stores only the hash, so it cannot be retrieved again.
      setLink(`${window.location.origin}/invite/${data.token}`);
      setEmail("");
    }
  }

  return (
    <section className="rounded-card border border-border bg-surface p-card" data-members-panel>
      <div className="flex items-baseline justify-between">
        <h2 className="font-heading text-lg font-medium text-ink">Members &amp; roles</h2>
        <span className="text-sm text-muted">{members.length} in this workspace</span>
      </div>

      {error ? (
        <p className="mt-3 rounded border border-danger bg-danger-bg p-2 text-sm text-danger">
          {error}
        </p>
      ) : null}

      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase text-muted">
              <th className="py-2 font-medium">Member</th>
              <th className="py-2 font-medium">Role</th>
              <th className="py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.user_id} data-member={m.user_id} className="border-b border-border">
                <td className="py-3">
                  <span className="block text-ink">
                    {m.full_name ?? m.email ?? `${m.user_id.slice(0, 8)}…`}
                  </span>
                  {m.email && m.full_name ? (
                    <span className="text-xs text-muted">{m.email}</span>
                  ) : null}
                </td>
                <td className="py-3">
                  {canManage && m.user_id !== currentUserId ? (
                    <select
                      data-role-select={m.user_id}
                      defaultValue={m.role}
                      disabled={busy}
                      onChange={(e) =>
                        call(`/api/workspaces/${workspaceId}/members/${m.user_id}`, {
                          method: "PATCH",
                          headers: { "content-type": "application/json" },
                          body: JSON.stringify({ role: e.target.value }),
                        })
                      }
                      className="rounded border border-border bg-surface px-2 py-1 text-sm"
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {label(r)}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-medium ${
                        ROLE_CHIP[m.role] ?? ROLE_CHIP.writer
                      }`}
                    >
                      {label(m.role)}
                    </span>
                  )}
                </td>
                <td className="py-3 text-right">
                  {canManage && m.user_id !== currentUserId ? (
                    <button
                      type="button"
                      data-remove-member={m.user_id}
                      disabled={busy}
                      onClick={() =>
                        call(`/api/workspaces/${workspaceId}/members/${m.user_id}`, {
                          method: "DELETE",
                        })
                      }
                      className="text-xs text-danger underline disabled:opacity-50"
                    >
                      Remove
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {invitations.length > 0 ? (
        <div className="mt-4">
          <h3 className="text-sm font-medium text-ink">Pending invitations</h3>
          <ul className="mt-2 space-y-1">
            {invitations.map((i) => (
              <li key={i.id} data-invitation={i.id} className="text-sm text-muted">
                {i.email} · {label(i.role)} · expires{" "}
                {new Date(i.expires_at).toLocaleDateString("en-IN")}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {canManage ? (
        <form onSubmit={invite} className="mt-5 border-t border-border pt-4">
          <h3 className="text-sm font-medium text-ink">Invite a member</h3>
          <div className="mt-2 flex flex-wrap gap-2">
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@firm.com"
              data-invite-email
              className="flex-1 rounded border border-border bg-surface px-3 py-2 text-sm"
            />
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              data-invite-role
              className="rounded border border-border bg-surface px-2 py-2 text-sm"
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {label(r)}
                </option>
              ))}
            </select>
            <button
              type="submit"
              disabled={busy}
              data-invite-submit
              className="rounded bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {busy ? "Inviting…" : "Invite"}
            </button>
          </div>
          {link ? (
            <div className="mt-3 rounded border border-primary bg-primary/5 p-3" data-invite-link>
              <p className="text-xs font-medium text-ink">
                Send this link to the invitee — it is shown once and cannot be retrieved
                again.
              </p>
              <code className="mt-1 block break-all text-xs text-primary">{link}</code>
            </div>
          ) : null}
        </form>
      ) : null}
    </section>
  );
}
