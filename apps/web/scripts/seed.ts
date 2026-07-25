/**
 * Idempotent seed — FIX-1 test user + workspace (docs/PRD.md §10).
 *
 * FIX-1: priya@meridian.test / role admin, workspace "Meridian Infotech Pvt Ltd".
 * Uses the legacy service JWT (accepted by every Supabase API incl. the auth admin API).
 * Run: pnpm seed  (env sourced from .env)
 */
const SB_URL = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const SERVICE = process.env.SUPABASE_SERVICE_JWT || process.env.SUPABASE_SERVICE_ROLE_KEY!;

const FIX1_EMAIL = "priya@meridian.test";
const FIX1_PASSWORD = "TenderCraft-FIX1!";
const WORKSPACE_NAME = "Meridian Infotech Pvt Ltd";

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

async function upsertWorkspace(name: string): Promise<string> {
  const existing = await j(
    await fetch(`${SB_URL}/rest/v1/workspaces?name=eq.${encodeURIComponent(name)}&select=id`, { headers: authHeaders }),
  );
  if (existing?.length) return existing[0].id;
  const created = await j(
    await fetch(`${SB_URL}/rest/v1/workspaces`, {
      method: "POST",
      headers: { ...authHeaders, Prefer: "return=representation" },
      body: JSON.stringify({ name }),
    }),
  );
  return created[0].id;
}

async function seedSampleTender(workspaceId: string) {
  // FIX-3: a tender with criteria incl. a sub-0.80 unconfirmed item, so the verification
  // queue (S4) shows the lock-blocked state (S4-D1) without needing a live upload.
  const existing = await j(
    await fetch(
      `${SB_URL}/rest/v1/tenders?workspace_id=eq.${workspaceId}&title=eq.${encodeURIComponent("Supply of 500 Desktop Computers")}&select=id`,
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
        workspace_id: workspaceId,
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
    { verbatim_text: "The bidder shall submit a declaration of non-blacklisting on company letterhead, signed by the authorized signatory.", category: "terms", requirement_level: "mandatory", confidence: 0.9, confirmed: true, anchor_page: 30, anchor_clause: "5.2", evidence_required: null, evaluation_weight: null },
  ];
  const criteria = raw.map((c) => ({ ...c, workspace_id: workspaceId, tender_id: tid }));
  const critRes = await fetch(`${SB_URL}/rest/v1/criteria`, {
    method: "POST",
    headers: authHeaders,
    body: JSON.stringify(criteria),
  });
  if (!critRes.ok) throw new Error(`criteria insert failed: ${critRes.status} ${await critRes.text()}`);
  console.log(`✓ FIX-3 tender "${tender[0].title}" (${criteria.length} criteria, 1 low-confidence) = ${tid}`);
}

async function seedProfile(workspaceId: string) {
  // FIX-2: vendor profile matching the design fixture (₹8.2 Cr avg turnover, MSE, expired ISO).
  const upsert = async (table: string, rows: unknown[], conflict?: string) => {
    const res = await fetch(`${SB_URL}/rest/v1/${table}${conflict ? `?on_conflict=${conflict}` : ""}`, {
      method: "POST",
      headers: { ...authHeaders, Prefer: "resolution=merge-duplicates" },
      body: JSON.stringify(rows.map((r) => ({ ...(r as object), workspace_id: workspaceId }))),
    });
    if (!res.ok) throw new Error(`${table} seed failed: ${res.status} ${await res.text()}`);
  };
  // clear child rows so re-seed is deterministic
  for (const t of ["profile_financials", "experience_records", "certifications"]) {
    await fetch(`${SB_URL}/rest/v1/${t}?workspace_id=eq.${workspaceId}`, { method: "DELETE", headers: authHeaders });
  }
  await upsert("vendor_profiles", [{
    cin: "U72200MH2011PTC214563", pan: "AAECM4321F", gst: "27AAECM4321F1ZP",
    udyam_registration: "UDYAM-MH-18-0034521", dpiit_registered: false,
    net_worth_cr: 4.3, working_capital_cr: 2.1, oem_status: "system_integrator",
  }], "workspace_id");
  await upsert("profile_financials", [
    { fy_label: "FY23", turnover_cr: 6.8 },
    { fy_label: "FY24", turnover_cr: 8.1 },
    { fy_label: "FY25", turnover_cr: 9.7 },
  ], "workspace_id,fy_label");
  // uniform keys (PGRST102): every row carries evidence_ref, null where absent
  await upsert("experience_records", [
    // Hardware works — comparable for the desktop-supply tender (FIX-3).
    { project_name: "District e-Governance rollout", client_type: "psu", value_cr: 3.4, scope_tags: ["hardware-supply", "installation"], completion_date: "2024-11-30", evidence_ref: "completion-cert-041.pdf" },
    { project_name: "PSU desktop refresh 800 units", client_type: "psu", value_cr: 2.6, scope_tags: ["hardware-supply"], completion_date: "2023-03-15", evidence_ref: null },
    { project_name: "Municipal CCTV network", client_type: "govt", value_cr: 2.1, scope_tags: ["surveillance", "installation"], completion_date: "2022-08-01", evidence_ref: null },
    { project_name: "Ministry IT infra (turnkey)", client_type: "govt", value_cr: 4.9, scope_tags: ["hardware-supply", "installation", "turnkey"], completion_date: "2025-01-20", evidence_ref: null },
    // Software/IT implementation works — comparable for the e-Office software tender (FIX-5).
    { project_name: "State e-Office & file-workflow software implementation", client_type: "govt", value_cr: 3.8, scope_tags: ["software-implementation", "workflow-automation"], completion_date: "2024-06-30", evidence_ref: "eoffice-completion-cert.pdf" },
    { project_name: "GST citizen-services portal development & rollout", client_type: "govt", value_cr: 2.9, scope_tags: ["software-development", "software-implementation"], completion_date: "2023-09-10", evidence_ref: null },
    { project_name: "Hospital Management Information System (HMIS) deployment", client_type: "psu", value_cr: 2.4, scope_tags: ["software-implementation"], completion_date: "2025-02-15", evidence_ref: null },
  ]);
  await upsert("certifications", [
    { name: "ISO 9001:2015", cert_no: "IN-9001-44821", valid_from: "2023-04-01", valid_to: "2026-03-31" },
    { name: "ISO 27001", cert_no: "IN-27001-9920", valid_from: "2024-09-01", valid_to: "2027-09-01" },
    { name: "CMMI L3", cert_no: "CMMI-3-5521", valid_from: "2025-01-01", valid_to: "2028-01-01" },
  ]);
  console.log("✓ FIX-2 vendor profile seeded (₹8.2 Cr avg turnover, MSE, ISO 9001 expired 03/2026)");
}

async function seedLibrary(workspaceId: string) {
  // FIX-4: content library docs (evidence corpus) with validity for the drafter/retrieval.
  await fetch(`${SB_URL}/rest/v1/library_documents?workspace_id=eq.${workspaceId}`, { method: "DELETE", headers: authHeaders });
  const docs = [
    { name: "turnover-certificate-FY25.pdf", doc_type: "financial", valid_to: null, text_content: "CA-certified statement: M/s Meridian Infotech recorded an average annual turnover of ₹8.2 Cr across FY23-FY25, with FY25 turnover of ₹9.7 Cr. Net worth ₹4.3 Cr.", structured_fields: { fy25_turnover_cr: 9.7, avg_turnover_cr: 8.2 } },
    { name: "iso-9001-2015-cert.pdf", doc_type: "certification", valid_to: "2026-03-31", text_content: "ISO 9001:2015 Quality Management certification, cert no. IN-9001-44821, issued to Meridian Infotech.", structured_fields: { cert_no: "IN-9001-44821" } },
    { name: "district-egovernance-completion-cert.pdf", doc_type: "completion", valid_to: null, text_content: "Completion certificate: District e-Governance hardware supply and installation, value ₹3.4 Cr, completed 11/2024 for a PSU client, executed satisfactorily.", structured_fields: { value_cr: 3.4 } },
    { name: "eoffice-completion-cert.pdf", doc_type: "completion", valid_to: null, text_content: "Completion certificate: State e-Office and file-workflow software implementation, value ₹3.8 Cr, completed 06/2024 for a Government department, delivered and accepted satisfactorily.", structured_fields: { value_cr: 3.8 } },
    { name: "gst-portal-completion-cert.pdf", doc_type: "completion", valid_to: null, text_content: "Completion certificate: GST citizen-services portal software development and rollout, value ₹2.9 Cr, completed 09/2023 for a Government client.", structured_fields: { value_cr: 2.9 } },
    { name: "hmis-completion-cert.pdf", doc_type: "completion", valid_to: null, text_content: "Completion certificate: Hospital Management Information System (HMIS) software deployment, value ₹2.4 Cr, completed 02/2025 for a PSU hospital.", structured_fields: { value_cr: 2.4 } },
    { name: "standard-undertaking-annexure1.docx", doc_type: "undertaking", valid_to: null, text_content: "Standard undertaking of non-blacklisting and compliance with tender terms, on company letterhead, signed by the authorized signatory.", structured_fields: {} },
    { name: "team-lead-cv-rahul-sharma.pdf", doc_type: "cv", valid_to: null, text_content: "Rahul Sharma, Project Lead. B.E. (Computer Science), PMP certified, 14 years experience in government IT hardware rollouts.", structured_fields: { qualification: "B.E., PMP" } },
  ].map((d) => ({ ...d, workspace_id: workspaceId }));
  const res = await fetch(`${SB_URL}/rest/v1/library_documents`, { method: "POST", headers: authHeaders, body: JSON.stringify(docs) });
  if (!res.ok) throw new Error(`library seed failed: ${res.status} ${await res.text()}`);
  console.log(`✓ FIX-4 content library: ${docs.length} documents (1 expired for validity-filter test)`);
}

async function seedWinnableTender(workspaceId: string) {
  // FIX-5: a tender this bidder actually qualifies for (₹5 Cr turnover threshold ≤ their ₹8.2 Cr,
  // similar works they have, an undertaking their library supports). Demonstrates the happy path.
  const title = "e-Office Software Implementation";
  const existing = await j(
    await fetch(`${SB_URL}/rest/v1/tenders?workspace_id=eq.${workspaceId}&title=eq.${encodeURIComponent(title)}&select=id`, { headers: authHeaders }),
  );
  for (const t of existing ?? []) {
    await fetch(`${SB_URL}/rest/v1/criteria?tender_id=eq.${t.id}`, { method: "DELETE", headers: authHeaders });
    await fetch(`${SB_URL}/rest/v1/tenders?id=eq.${t.id}`, { method: "DELETE", headers: authHeaders });
  }
  const tender = await j(
    await fetch(`${SB_URL}/rest/v1/tenders`, {
      method: "POST",
      headers: { ...authHeaders, Prefer: "return=representation" },
      body: JSON.stringify({ workspace_id: workspaceId, title, tender_number: "MAHA/IT/2026/4415", authority: "MahaIT", status: "verification" }),
    }),
  );
  const tid = tender[0].id;
  const criteria = [
    { verbatim_text: "Average annual turnover of not less than ₹5 Crores over FY23–FY25.", category: "eligibility", requirement_level: "mandatory", confidence: 0.95, confirmed: true, anchor_page: 8, anchor_clause: "3.1(a)", evidence_required: null, evaluation_weight: null },
    { verbatim_text: "At least three similar works of software/IT implementation, each ≥ ₹2 Cr.", category: "eligibility", requirement_level: "mandatory", confidence: 0.9, confirmed: true, anchor_page: 8, anchor_clause: "3.1(c)", evidence_required: null, evaluation_weight: null },
    { verbatim_text: "Declaration of non-blacklisting on company letterhead.", category: "terms", requirement_level: "mandatory", confidence: 0.92, confirmed: true, anchor_page: 15, anchor_clause: "5.1", evidence_required: null, evaluation_weight: null },
  ].map((c) => ({ ...c, workspace_id: workspaceId, tender_id: tid }));
  const res = await fetch(`${SB_URL}/rest/v1/criteria`, { method: "POST", headers: authHeaders, body: JSON.stringify(criteria) });
  if (!res.ok) throw new Error(`winnable criteria failed: ${res.status} ${await res.text()}`);
  console.log(`✓ FIX-5 winnable tender "${title}" (${criteria.length} criteria bidder meets) = ${tid}`);
}

async function main() {
  console.log("seeding FIX-1…");
  await deleteExistingUser(FIX1_EMAIL);
  const workspaceId = await upsertWorkspace(WORKSPACE_NAME);
  await seedProfile(workspaceId);
  await seedLibrary(workspaceId);
  await seedSampleTender(workspaceId);
  await seedWinnableTender(workspaceId);

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
    // email/full_name are what the members roster renders — without them it falls back
    // to a truncated UUID, which is the bug migration 0013 exists to fix.
    body: JSON.stringify({
      user_id: user.id,
      workspace_id: workspaceId,
      active_workspace_id: workspaceId,
      role: "admin",
      email: FIX1_EMAIL,
      full_name: "Priya Sharma",
    }),
  });

  console.log(`✓ FIX-1 ready: ${FIX1_EMAIL} / ${FIX1_PASSWORD}`);
  // Since 0011 a profiles row alone grants NOTHING: current_workspace_id() validates the
  // active workspace against workspace_members. Seed both or the user sees zero rows.
  await fetch(`${SB_URL}/rest/v1/workspace_members?on_conflict=user_id,workspace_id`, {
    method: "POST",
    headers: { ...authHeaders, Prefer: "resolution=merge-duplicates" },
    body: JSON.stringify({ user_id: user.id, workspace_id: workspaceId, role: "admin" }),
  });

  console.log(`  workspace "${WORKSPACE_NAME}" = ${workspaceId}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
