import { cache } from "react";

import { createClient } from "@/lib/supabase/server";

/** Server-side proxy to the evaluate engine, forwarding the user's JWT.
 *  The engine derives the authority from that token — never from anything we send. */
export async function engineFetch(path: string, init?: RequestInit): Promise<Response> {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) {
    return new Response(
      JSON.stringify({ ok: false, data: null, error: { code: "NO_SESSION", message: "not signed in" } }),
      { status: 401 },
    );
  }
  return fetch(`${process.env.EVAL_ENGINE_URL}${path}`, {
    ...init,
    headers: { ...init?.headers, Authorization: `Bearer ${session.access_token}` },
    cache: "no-store",
  });
}

export type EngineResult<T> = { ok: boolean; data: T | null; code?: string; message?: string };

export async function engineJson<T>(path: string): Promise<EngineResult<T>> {
  const res = await engineFetch(path);
  const body = await res.json().catch(() => null);
  if (!body) return { ok: false, data: null, code: "BAD_RESPONSE" };
  return { ok: body.ok, data: body.data, code: body.error?.code, message: body.error?.message };
}

/**
 * Deduped readers.
 *
 * A nested layout and the page inside it both need the evaluation — without cache() that is
 * two identical engine round trips per navigation. React's cache() dedupes within one server
 * render pass, which is exactly this case. The bidder product shipped the same shape as a bug
 * (`/submission` re-running the whole of `/readiness`) and it cost seconds per page; this
 * starts with the fix rather than earning it back later.
 *
 * Note the argument-identity rule: cache() keys on the arguments, so these must be called with
 * the same id string from both places, not with objects that merely look equal.
 */
export type Me = { user_id: string; authority_id: string; authority_name: string | null; role: string };

export const getMe = cache(() => engineJson<Me>("/api/me"));

export type EvaluationDetail = {
  evaluation: {
    id: string;
    title: string;
    tender_number: string | null;
    technical_weight: number;
    financial_weight: number;
    qualifying_marks: number;
    quorum: number;
    tie_break_rule: string | null;
    framework_locked_at: string | null;
    technical_locked_at: string | null;
  };
  criteria: {
    id: string; kind: string; text: string; max_marks: number;
    anchor_page: number | null; anchor_clause: string | null;
  }[];
  unconfirmed: number;
  bids: { id: string; bidder_name: string; responsive: boolean | null }[];
  members: { user_id: string; full_name: string | null; email: string; role: string }[];
  coi: { user_id: string }[];
};

export const getEvaluation = cache((id: string) =>
  engineJson<EvaluationDetail>(`/api/evaluations/${id}`),
);

export type TechnicalState = {
  locked_at: string | null;
  quorum: number;
  submitted_evaluators: number;
  qualifying_marks: number;
  max_technical_marks: number;
  bids: {
    bid_id: string; bidder_name: string; total: string | null; qualified: boolean;
    criteria: {
      criterion_id: string; criterion: string; max_marks: number; marks: string[];
      spread: string; requires_consensus: boolean; consensus: string | null;
      committee_mark: string | null;
    }[];
  }[];
  blockers: { code: string; detail: string }[];
  can_lock: boolean;
};

export const getTechnical = cache((id: string) =>
  engineJson<TechnicalState>(`/api/evaluations/${id}/technical`),
);
