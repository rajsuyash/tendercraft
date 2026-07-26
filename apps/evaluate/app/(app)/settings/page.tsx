import { engineJson } from "@/lib/engine";

type Members = {
  authority: { name: string } | null;
  members: { user_id: string; full_name: string | null; email: string; role: string }[];
};

const ROLE_LABEL: Record<string, string> = {
  officer: "Procurement Officer",
  chair: "TEC Chair",
  member: "TEC Member",
  auditor: "Audit / Vigilance",
};

const ROLE_CAN: Record<string, string> = {
  officer: "Owns evaluations, screens bids, opens financial envelopes",
  chair: "Scores, records consensus marks, locks technical scores",
  member: "Scores bids independently",
  auditor: "Reads everything, including the audit trail. Cannot modify anything.",
};

export default async function SettingsPage() {
  const res = await engineJson<Members>("/api/members");
  const members = res.data?.members ?? [];

  return (
    <main className="mx-auto max-w-4xl px-page py-page">
      <h1 className="font-heading text-2xl font-semibold text-ink">Settings</h1>
      <p className="mt-1 text-sm text-muted">{res.data?.authority?.name ?? "Authority"}</p>

      <section className="mt-6 rounded-card border border-border bg-surface">
        <div className="border-b border-border p-card">
          <h2 className="font-heading text-base font-medium text-ink">Members and roles</h2>
          <p className="mt-1 text-sm text-muted">
            Roles decide what a person can do inside this authority. They are enforced by the
            engine on every request, not by hiding buttons.
          </p>
        </div>
        <ul className="divide-y divide-border">
          {members.map((m) => (
            <li key={m.user_id} className="flex flex-wrap items-start justify-between gap-3 p-card">
              <div className="min-w-0">
                <p className="text-sm text-ink">{m.full_name ?? m.email}</p>
                <p className="text-xs text-muted">{m.email}</p>
              </div>
              <div className="text-right">
                <span className="rounded-full bg-primary-tint px-2.5 py-0.5 text-xs font-medium text-primary">
                  {ROLE_LABEL[m.role] ?? m.role}
                </span>
                <p className="mt-1 max-w-xs text-xs text-muted">{ROLE_CAN[m.role] ?? ""}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <p className="mt-4 rounded-card border border-border bg-surface-alt p-card text-sm text-muted">
        Member management is read-only in this demo. Inviting and removing members, and changing
        roles, are specified in the PRD (F1, F4) and are not built yet — rather than showing you
        controls that would not work.
      </p>
    </main>
  );
}
