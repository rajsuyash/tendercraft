-- RBAC: add the one genuinely missing role.
--
-- 'viewer' — an engagement partner with visibility across pursuits who must never touch a
-- draft. A real Big Four role with nowhere to sit in the existing six.
--
-- Org-level authority is profiles.is_org_admin (added in 0011), deliberately a boolean
-- rather than a second enum: one flag beats a parallel hierarchy.
--
-- Postgres cannot use a new enum value in the same transaction that adds it, so this is
-- its own migration with nothing else in it. Idempotent.

alter type public.user_role add value if not exists 'viewer';
