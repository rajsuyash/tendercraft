-- The forwarded GeM email, and the action it creates (UML asks 4 and 1's acquisition half).
--
-- The ask: "After the technical evaluation of a bid, GeM may require additional documents or
-- clarifications. The system should monitor the tender status and identify such requirements
-- as soon as they are generated on the portal."
--
-- 0034 answered the half a public page can answer: the evaluation STAGE. This answers the
-- other half, and it is the only legal way to. The request itself is addressed to one bidder
-- about their own submission, it is on no public page, and reading it out of the customer's
-- GeM account is refused by G-1 and G-8 permanently. What is left is the customer forwarding
-- their own mail to an address we own — no portal credential, nothing scraped, no rule bent.
--
-- **Why this ships before anyone has seen a real GeM email.** It was blocked on "ask UML to
-- forward three samples" since 2026-08-07 and the parse was called unspecifiable. That is only
-- true of a parser that must be right. `deterministic/inbound.py` is built to be wrong:
-- classification decides ROUTING, never RETENTION, so the worst case is an email filed as
-- `unclassified` with its text one click away — which still beats a human finding it in
-- Outlook. Samples improve precision later; they were never needed to start.
--
-- Two tables because they answer different questions and have different lifetimes:
-- what arrived (evidence, immutable) and what someone must do about it (state, resolvable).

-- The address a customer forwards to. A random token rather than the workspace UUID, for two
-- separate reasons: a UUID in an email address is unreadable to the human setting up a mail
-- rule, and it is also a workspace identifier that appears in other people's inboxes the
-- moment anyone forwards a thread. A token can be rotated after that happens; a UUID cannot.
--
-- Backfilled in the same migration, because a column only one code path writes leaves every
-- pre-existing row rendering as the fallback — which here would be a workspace whose inbound
-- address silently does not exist (docs/known-pitfalls.md).
alter table public.workspaces
  add column if not exists inbound_token text;

update public.workspaces
   set inbound_token = encode(gen_random_bytes(6), 'hex')
 where inbound_token is null;

create unique index if not exists workspaces_inbound_token_uniq
  on public.workspaces(inbound_token) where inbound_token is not null;

comment on column public.workspaces.inbound_token is
  'Local part of this workspace''s forwarding address (<token>@<DISCOVERY_INBOUND_DOMAIN>). '
  'Rotatable: it ends up in other people''s inboxes whenever a thread is forwarded onward.';


create table if not exists public.inbound_messages (
  id                uuid primary key default gen_random_uuid(),
  workspace_id      uuid not null references public.workspaces(id) on delete cascade,
  -- The address the provider delivered to. This is how a message finds its workspace, so it
  -- is stored as received: a support ticket that begins "we forwarded it and nothing happened"
  -- is unanswerable without knowing exactly what address the mail actually reached.
  delivered_to      text not null,
  from_address      text,
  subject           text,
  -- Kept whole and never summarised away. The parser will be wrong about real GeM mail before
  -- it is right, and re-parsing the original is the only way to fix a class of mistake rather
  -- than one instance of it. It is also the provenance for any action taken below.
  body_text         text not null default '',
  -- The provider's own id, where it gives one. UNIQUE per workspace because every inbound
  -- provider retries on a non-2xx and at-least-once delivery is the norm: without this a
  -- retried webhook creates a second action for one request, and a bidder responds twice to a
  -- buyer. Nullable because not every provider supplies one; the digest below covers that case.
  provider_message_id text,
  -- sha256 of (delivered_to, from, subject, body). The dedup key when the provider gives no id.
  content_digest    text not null,
  kind              text not null default 'unclassified'
    check (kind in ('clarification_request','stage_notice','bid_alert','unclassified')),
  -- Which phrases drove the classification. A misclassification must be diagnosable from the
  -- stored row, not by re-running a parser against an email somebody has since deleted.
  matched_phrases   text[] not null default '{}',
  bid_refs          text[] not null default '{}',
  received_at       timestamptz not null default now(),
  created_at        timestamptz not null default now()
);

-- Both dedup keys, scoped by workspace. Two customers legitimately forward the same GeM
-- broadcast, and a global unique would silently drop the second one's copy — the tenant would
-- simply never see a tender, with nothing anywhere reporting why (ET-7).
create unique index if not exists inbound_messages_provider_id_uniq
  on public.inbound_messages(workspace_id, provider_message_id)
  where provider_message_id is not null;

create unique index if not exists inbound_messages_digest_uniq
  on public.inbound_messages(workspace_id, content_digest);

create index if not exists inbound_messages_workspace_received_idx
  on public.inbound_messages(workspace_id, received_at desc, id desc);


create table if not exists public.bid_actions (
  id              uuid primary key default gen_random_uuid(),
  workspace_id    uuid not null references public.workspaces(id) on delete cascade,
  -- The tender this is about, when the message named exactly one. NULL is a real and common
  -- state — a digest naming three bids, or a mail naming none — and the action still exists
  -- and is still shown. Guessing which tender a document request belongs to would attach a
  -- deadline to the wrong bid, which looks like a working feature until the wrong one lapses.
  opportunity_id  uuid references public.opportunities(id) on delete set null,
  -- Kept even when opportunity_id is NULL: it is what a human needs to find the bid manually,
  -- and what a later sweep uses to link the action once that tender enters the corpus.
  portal_ref_no   text,
  source_message  uuid references public.inbound_messages(id) on delete set null,
  kind            text not null
    check (kind in ('clarification_request','stage_notice')),
  summary         text not null,
  -- ONLY ever set from a date the email explicitly presents as a deadline. Never inferred,
  -- never defaulted to "7 days" — a wrong date on a compliance action is the single output of
  -- this feature that could lose a bid outright, and NULL correctly means "ask the human".
  due_at          date,
  resolved_at     timestamptz,
  resolved_by     uuid,
  created_at      timestamptz not null default now()
);

create index if not exists bid_actions_open_idx
  on public.bid_actions(workspace_id, due_at nulls last)
  where resolved_at is null;

create index if not exists bid_actions_opportunity_idx
  on public.bid_actions(workspace_id, opportunity_id);


alter table public.inbound_messages enable row level security;
alter table public.bid_actions enable row level security;

create policy inbound_messages_workspace_all on public.inbound_messages for all
  using (workspace_id = public.current_workspace_id())
  with check (workspace_id = public.current_workspace_id());

create policy bid_actions_workspace_all on public.bid_actions for all
  using (workspace_id = public.current_workspace_id())
  with check (workspace_id = public.current_workspace_id());


comment on table public.inbound_messages is
  'Emails a customer forwarded to their workspace address. The ONLY legal route to a GeM '
  'post-technical-evaluation document request: it is addressed to one bidder, is on no public '
  'page, and reading it from their GeM account is refused by G-1/G-8. Body text is untrusted '
  'input (G-6) — it is matched and counted, never interpreted, and never reaches a model.';

comment on column public.bid_actions.due_at is
  'Set only from a date the message explicitly calls a deadline. NULL means none was readable '
  'and a human must supply it — never a default or an estimate.';

comment on column public.bid_actions.opportunity_id is
  'NULL when the message named zero or several bids. The action is still created and shown; '
  'linking it by guess would put a real deadline on the wrong tender.';
