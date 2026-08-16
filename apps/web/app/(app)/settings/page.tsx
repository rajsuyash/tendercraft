import { AlertSettings, type NotificationSettings } from "@/components/AlertSettings";
import { MembersPanel, type Invitation, type Member } from "@/components/MembersPanel";
import { engineFetch } from "@/lib/engine";
import { createClient } from "@/lib/supabase/server";

// S12 — Workspace Settings. Read-mostly: RBAC roster, approval chain, immutable
// audit log, deadline-escalation config (E-FR1–E-FR4, E-FR6).

type Role = "writer" | "reviewer" | "compliance_checker" | "legal" | "approver" | "admin";

const ROLE_CHIP: Record<Role, string> = {
  writer: "border border-border bg-surface text-ink",
  reviewer: "bg-warning-bg text-warning",
  compliance_checker: "bg-info-bg text-info",
  legal: "bg-info-bg text-info",
  approver: "bg-success-bg text-success",
  admin: "bg-primary text-on-primary",
};

const CHAIN: Role[] = ["writer", "reviewer", "compliance_checker", "approver"];

const ESCALATION_THRESHOLDS = [
  { id: "t-72h", label: "T-72h Warning", recipients: ["Bid owner"], channels: "Email only" },
  {
    id: "t-48h",
    label: "T-48h Escalation",
    recipients: ["Bid owner", "Approver"],
    channels: "Email + in-app",
  },
  {
    id: "t-24h",
    label: "T-24h Critical",
    recipients: ["Bid owner", "Approver", "Admin"],
    channels: "Email + in-app + SMS",
  },
] as const;

function roleLabel(role: Role): string {
  return role
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function RoleChip({ role }: { role: Role }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${ROLE_CHIP[role]}`}
    >
      {roleLabel(role)}
    </span>
  );
}

export default async function SettingsPage() {
  const supabase = await createClient();

  // Members come from the ENGINE, not a direct Supabase read: the roster needs the
  // workspace_members join and profile identity, and the old direct query could only ever
  // return one row (profiles_self_select).
  // The audit log needs nothing from /api/me, so it goes out alongside it rather than after.
  const [meRes, { data: auditEvents }] = await Promise.all([
    engineFetch("/api/me"),
    supabase
      .from("audit_events")
      .select("id,actor,action,entity,entity_id,created_at")
      .order("created_at", { ascending: false })
      .limit(20),
  ]);
  const me = meRes.ok ? (await meRes.json()).data : null;

  // Round 2 — both of these need the resolved workspace id, and neither needs the other.
  const [membersRes, { data: workspace }, alertsRes] = await Promise.all([
    me?.workspace_id ? engineFetch(`/api/workspaces/${me.workspace_id}/members`) : null,
    supabase
      .from("workspaces")
      .select("name")
      .eq("id", me?.workspace_id ?? "")
      .maybeSingle(),
    engineFetch("/api/notifications/settings"),
  ]);

  const alertsBody = alertsRes.ok ? await alertsRes.json().catch(() => null) : null;
  // Alerts default to OFF rather than to an error state: a workspace that has never opened
  // this panel is not broken, it simply has not opted in.
  const alerts: NotificationSettings = alertsBody?.ok
    ? (alertsBody.data as NotificationSettings)
    : {
        enabled: false,
        recipients: [],
        min_band: "medium",
        notify_assignee: true,
        smtp_configured: false,
      };

  let members: Member[] = [];
  let invitations: Invitation[] = [];
  if (membersRes?.ok) {
    const body = await membersRes.json();
    if (body.ok) {
      members = body.data.members as Member[];
      invitations = body.data.invitations as Invitation[];
    }
  }

  return (
    <main className="p-page">
      <header className="mb-6">
        <h1 className="font-heading text-2xl font-semibold text-ink">
          Workspace — {workspace?.name ?? "—"}
        </h1>
        <p className="text-sm text-muted">
          Manage enterprise settings, roles, and compliance workflows.
        </p>
      </header>

      <nav className="mb-6 flex gap-6 border-b border-border text-sm">
        {["Members & Roles", "Approval chains", "Audit log", "Deadlines & alerts"].map((tab) => (
          <span key={tab} className="border-b-2 border-transparent py-2 text-muted first:border-primary first:text-ink first:font-medium">
            {tab}
          </span>
        ))}
      </nav>

      <div className="mb-8">
        <MembersPanel
          workspaceId={me?.workspace_id ?? ""}
          members={members}
          invitations={invitations}
          canManage={me?.role === "admin"}
          currentUserId={me?.user_id ?? ""}
        />
      </div>

      <div className="mb-8">
        <AlertSettings initial={alerts} />
      </div>

      <section className="mb-8">
        <h2 className="mb-3 font-heading text-lg font-semibold text-ink">Approval chains</h2>
        <div className="rounded-card border border-border bg-surface p-card">
          <p className="mb-4 text-sm text-muted">
            Defines the mandatory sequence before PDF/DOCX export is permitted.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            {CHAIN.map((role, i) => (
              <div key={role} className="flex items-center gap-3">
                <div className="rounded-card border border-border bg-surface-alt px-4 py-3">
                  <RoleChip role={role} />
                </div>
                {i < CHAIN.length - 1 && <span className="text-muted">→</span>}
              </div>
            ))}
          </div>
          <p className="mt-4 text-xs text-muted">
            Export locks until all required approvals complete (admin override is logged).
          </p>
        </div>
      </section>

      <section className="mb-8">
        <h2 className="mb-3 font-heading text-lg font-semibold text-ink">Audit log</h2>
        <div className="rounded-card border border-border bg-surface">
          <ul>
            {(auditEvents ?? []).map((e) => (
              <li
                key={e.id}
                data-audit-event
                className="flex items-center gap-4 border-b border-border p-card text-sm last:border-0"
              >
                <span className="font-mono text-xs text-muted">{e.created_at}</span>
                <span className="text-ink">{e.action}</span>
                <span className="text-muted">{e.entity}</span>
                <span className="ml-auto font-mono text-xs text-muted">
                  {e.actor ? `${e.actor.slice(0, 8)}…` : "system"}
                </span>
              </li>
            ))}
            {(auditEvents ?? []).length === 0 && (
              <li className="p-card text-sm text-muted">No audit events yet.</li>
            )}
          </ul>
        </div>
      </section>

      <section>
        <h2 className="mb-3 font-heading text-lg font-semibold text-ink">Deadlines & alerts</h2>
        <div className="space-y-3">
          {ESCALATION_THRESHOLDS.map((t) => (
            <div
              key={t.id}
              data-escalation-threshold
              className="flex items-center justify-between rounded-card border border-border bg-surface p-card"
            >
              <div>
                <p className="font-medium text-ink">{t.label}</p>
                <p className="text-xs text-muted">{t.channels}</p>
              </div>
              <div className="flex gap-2">
                {t.recipients.map((r) => (
                  <span
                    key={r}
                    className="rounded-full bg-primary-tint px-2.5 py-0.5 text-xs font-medium text-primary"
                  >
                    {r}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
