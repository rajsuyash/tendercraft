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

async function seedSampleTender(tenantId: string) {
  // FIX-3: a tender with criteria incl. a sub-0.80 unconfirmed item, so the verification
  // queue (S4) shows the lock-blocked state (S4-D1) without needing a live upload.
  const existing = await j(
    await fetch(
      `${SB_URL}/rest/v1/tenders?tenant_id=eq.${tenantId}&title=eq.${encodeURIComponent("Supply of 500 Desktop Computers")}&select=id`,
      { headers: authHeaders },
    ),
  );
  for (const t of existing ?? []) {
    await fetch(`${SB_URL}/rest/v1/criteria?tender_id=eq.${t.id}`, { method: "DELETE", headers: authHeaders });
    await fetch(`${SB_URL}/rest/v1/tenders?id=eq.${t.id}`, { method: "DELETE", headers: authHeaders });
  }
  const tender = await j(
    await fetch(`${SB_URL}/rest/v1/tenders`, {
      method: "POST",
      headers: { ...authHeaders, Prefer: "return=representation" },
      body: JSON.stringify({
        tenant_id: tenantId,
        title: "Supply of 500 Desktop Computers",
        tender_number: "GEM/2026/B/5127401",
        authority: "National Informatics Centre",
        status: "verification",
      }),
    }),
  );
  const tid = tender[0].id;
  // PostgREST bulk insert requires uniform keys across all rows — every object has the
  // same shape (missing values as null).
  const raw = [
    { verbatim_text: "Average annual turnover of not less than ₹10 Crores over FY23–FY25.", category: "eligibility", requirement_level: "mandatory", confidence: 0.95, confirmed: true, anchor_page: 12, anchor_clause: "4.1(a)", evidence_required: "CA-certified turnover certificate", evaluation_weight: null },
    { verbatim_text: "Three similar works of comparable nature, each ≥ ₹2 Cr.", category: "eligibility", requirement_level: "mandatory", confidence: 0.82, confirmed: true, anchor_page: 13, anchor_clause: "4.1(c)", evidence_required: null, evaluation_weight: null },
    { verbatim_text: "Valid ISO 9001:2015 certification on the bid date.", category: "technical", requirement_level: "desirable", confidence: 0.88, confirmed: true, anchor_page: 14, anchor_clause: "4.2", evidence_required: null, evaluation_weight: 5 },
    { verbatim_text: "OEM Manufacturer's Authorization Form in Annexure-VII.", category: "eligibility", requirement_level: "mandatory", confidence: 0.61, confirmed: false, anchor_page: 22, anchor_clause: "Annexure-VII", evidence_required: null, evaluation_weight: null },
  ];
  const criteria = raw.map((c) => ({ ...c, tenant_id: tenantId, tender_id: tid }));
  const critRes = await fetch(`${SB_URL}/rest/v1/criteria`, {
    method: "POST",
    headers: authHeaders,
    body: JSON.stringify(criteria),
  });
  if (!critRes.ok) throw new Error(`criteria insert failed: ${critRes.status} ${await critRes.text()}`);
  console.log(`✓ FIX-3 tender "${tender[0].title}" (${criteria.length} criteria, 1 low-confidence) = ${tid}`);
}

async function main() {
  console.log("seeding FIX-1…");
  await deleteExistingUser(FIX1_EMAIL);
  const tenantId = await upsertTenant(TENANT_NAME);
  await seedSampleTender(tenantId);

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
