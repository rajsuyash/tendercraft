/**
 * Idempotent seed — FIX-1 test user + tenant (docs/PRD.md §10).
 *
 * FIX-1: priya@meridian.test / role admin, tenant "Meridian Infotech Pvt Ltd".
 * Uses the legacy service JWT (accepted by every Supabase API incl. the auth admin API).
 * Run: pnpm seed  (env sourced from .env)
 */
const SB_URL = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const SERVICE = process.env.SUPABASE_SERVICE_JWT || process.env.SUPABASE_SERVICE_ROLE_KEY!;

const FIX1_EMAIL = "priya@meridian.test";
const FIX1_PASSWORD = "TenderCraft-FIX1!";
const TENANT_NAME = "Meridian Infotech Pvt Ltd";

if (!SB_URL || !SERVICE) {
  throw new Error("seed: NEXT_PUBLIC_SUPABASE_URL and a service key must be set in .env");
}
if (process.env.NODE_ENV === "production") {
  throw new Error("seed: refusing to run with NODE_ENV=production (creates/deletes test users)");
}

const authHeaders = { apikey: SERVICE, Authorization: `Bearer ${SERVICE}`, "Content-Type": "application/json" };

async function j(res: Response) {
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

async function deleteExistingUser(email: string) {
  const res = await fetch(`${SB_URL}/auth/v1/admin/users`, { headers: authHeaders });
  const data = await j(res);
  for (const u of data?.users ?? []) {
    if (u.email === email) await fetch(`${SB_URL}/auth/v1/admin/users/${u.id}`, { method: "DELETE", headers: authHeaders });
  }
}

async function upsertTenant(name: string): Promise<string> {
  const existing = await j(
    await fetch(`${SB_URL}/rest/v1/tenants?name=eq.${encodeURIComponent(name)}&select=id`, { headers: authHeaders }),
  );
  if (existing?.length) return existing[0].id;
  const created = await j(
    await fetch(`${SB_URL}/rest/v1/tenants`, {
      method: "POST",
      headers: { ...authHeaders, Prefer: "return=representation" },
      body: JSON.stringify({ name }),
    }),
  );
  return created[0].id;
}

async function main() {
  console.log("seeding FIX-1…");
  await deleteExistingUser(FIX1_EMAIL);
  const tenantId = await upsertTenant(TENANT_NAME);

  const user = await j(
    await fetch(`${SB_URL}/auth/v1/admin/users`, {
      method: "POST",
      headers: authHeaders,
      body: JSON.stringify({ email: FIX1_EMAIL, password: FIX1_PASSWORD, email_confirm: true }),
    }),
  );
  if (!user?.id) throw new Error(`create user failed: ${JSON.stringify(user)}`);

  await fetch(`${SB_URL}/rest/v1/profiles`, {
    method: "POST",
    headers: { ...authHeaders, Prefer: "resolution=merge-duplicates" },
    body: JSON.stringify({ user_id: user.id, tenant_id: tenantId, role: "admin" }),
  });

  console.log(`✓ FIX-1 ready: ${FIX1_EMAIL} / ${FIX1_PASSWORD}`);
  console.log(`  tenant "${TENANT_NAME}" = ${tenantId}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
