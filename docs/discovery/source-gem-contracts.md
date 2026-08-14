# Source review — GeM awarded contracts (`gem.gov.in/view_contracts`)

**Probed:** 2026-08-07 · **Verdict: acquisition REFUSED — G-8 (CAPTCHA).**
**Prompted by:** `docs/feedback/usha-martin.md` ask 5, five-year historical price analysis,
which UML named their major pain area.
**Method:** one `GET` through the existing `services/gem-connector/app/fetch.py::GuardedFetcher`
— identified UA, robots check, 1 rps cap, byte cap, no auto-redirect. The allowlist was widened
in a scratchpad probe script, never in `app/fetch.py`.

This file exists to stop the question being re-asked. The answer is not "hard", it is "no by a
rule we wrote ourselves", and the useful part is §4 — what *is* available instead.

## 1. What was verified

| Check | Result |
|---|---|
| Reachable without login | **Yes** — `HTTP 200`, 3.2 MB `text/html`, no auth |
| `robots.txt` | **Permits it** — `gem.gov.in/robots.txt` disallows only `/cgi-bin/` and `/resources/` |
| Commercial bot-defence (Cloudflare / Imperva / reCAPTCHA / hCaptcha) | **None** — `assert_no_bot_challenge` clean |
| CSRF token | Absent (unlike `/all-bids`) |
| **GeM's own CAPTCHA on the search** | **Present, required, on both forms** |

Two search forms, both gated:

- `frm1` — search by contract / bid / RA number. Field `captcha_entered1`, hidden `h_captcha1`.
- `frm` — search by ministry, state, department, organisation and date range. Field
  `captcha_entered2`, hidden `h_captcha2`.

Both render `<label>Enter captcha code<span class="red req_date_bid">*</span></label>` — the same
required-marker class the mandatory date fields use. The entered code is encrypted client-side
before submission:

```js
$.ajax({ type: "POST", async: false, data: { 'str': plainStr },
         url: 'https://gem.gov.in/view_contracts/encryptCaptcha',
         success: function(response) { encResp = response.trim(); } })
```

There is no unauthenticated, un-captcha'd path to a result set on this page.

## 2. Why that is a refusal and not an obstacle

`docs/discovery/PRD.md` §0, non-goals, verbatim: *"no authenticated acquisition, **no CAPTCHA
bypass**, no IP rotation, no portal write path of any kind (G-1, G-8)."*

Solving, OCR-ing, outsourcing or replaying that captcha is the prohibited act named in our own
agent contract. It is also the guardrail whose credibility the evaluate product depends on
(F13) — we sell a government buyer the claim that we do not circumvent portal controls. There
is no version of ask 5 that goes through this endpoint.

The distinction against the bid listing is worth keeping straight, because they look similar and
are not: `bidplus.gem.gov.in/all-bids-data` needs an **anonymous session cookie acquired from a
public page**, which `source-gem.md` correctly argued is not a credential. A captcha is not a
session — it is an explicit assertion by the portal that this surface is for humans, and the
whole point of G-8 is that we take that at face value.

## 3. A gap this probe exposed in our own tooling

`GuardedFetcher`'s `_CHALLENGE_MARKERS` (`fetch.py:66-78`) looks for `cf-challenge`, `incapsula`,
`imperva`, `distil`, `recaptcha`, `hcaptcha`. **It does not catch a portal's own home-grown
captcha** — `encryptCaptcha` / `captcha_entered` / `h_captcha` match nothing in that list, so
`assert_no_bot_challenge` returned clean on a page that is unambiguously captcha-gated.

The marker list was written to detect *a portal turning defensive mid-run*. It is not a
"is this surface automatable" test, and a future source review must not treat a clean
`assert_no_bot_challenge` as permission. Add the generic markers (`captcha_entered`, `h_captcha`,
`encryptcaptcha`, `captcha_code`) so a run halts rather than submitting a blank field and
recording an empty result set as "no contracts found".

## 4. What is actually available for price history

In cost order. The first is free and the customer already owns the data.

1. **UML's own contract history.** They are the seller on every contract they won — the award
   values are *their* records, in their possession, and theirs to give us. This is the only
   route that needs no permission from anyone, and it lands in a table that already exists:
   `past_bids` / `answers` (migration 0027), whose `outcome` is user-supplied by design
   precisely because *"we cannot see an award notice"* (`app/past_bids_routes.py:155`). It also
   feeds the gate that suppresses Module D — `deterministic/suppression.py` withholds every
   score estimate until ≥30 comparable outcomes exist (D-AC4). **Ask 5 and Module D are the same
   corpus.** Limitation, stated plainly: it is UML's own history, not the market's, so it prices
   *their* past bids and not competitors'.
2. **The GeM SPV permission letter.** Still unsent (`source-gem.md` §8 item 5, named
   2026-07-30). A written grant is the mechanism their own policy names, and it is the only
   thing that could open a non-captcha route. Costs a letter, unknown lead time, non-zero
   chance. Send it.
3. **A licensed commercial GeM data vendor.** `source-gem.md` rejected these at ~$200/mo as
   "data we can acquire compliantly ourselves" — that reasoning held for the *listing* and does
   not hold here, because the contracts surface is one we have now established we cannot
   acquire ourselves at all. **Do not act on this before 1 and 2**: option 1 is free and may
   satisfy UML on its own, and a subscription bought to answer one design partner's ask before
   they have committed (`usha-martin.md` assumption 7) is the wrong order.
4. **UML's own authenticated GeM view.** They can see their own contracts logged in. We will
   not hold that credential (G-1) and will not automate that session (G-8). If the data is to
   come from there, a human at UML exports it — which collapses into option 1.

## 5. Not probed

- Whether the result set, once a human solves the captcha, carries **per-item unit prices** or
  only contract totals. Unanswerable without submitting the form, and moot given §2.
- Whether any other public GeM surface publishes award data without a captcha (an open-data
  portal, a statistics dashboard, a bulk download). **Worth one hour before accepting §4** — the
  refusal here is about this endpoint, not about every GeM surface.
- `data.gov.in` as a publisher of GeM transaction data. Searched, nothing conclusive found;
  a proper look belongs with the item above.

## 6. Registry entry

None. Nothing here is fetchable, so no source is added — recording this as a registry entry
with a "blocked" flag would put a host in the allowlist that must never be swept.

```
gem_contracts:
  STATUS: NOT REGISTERED — acquisition refused
  url: https://gem.gov.in/view_contracts
  robots_reviewed: 2026-08-07   (permitted)
  terms_reviewed: 2026-07-30    (source-gem.md §8 — reproduction clause, unchanged)
  blocker: CAPTCHA on both search forms (G-8, PRD §0 non-goal)
  reviewer: <human sign-off not required — nothing to approve>
```

None of this is legal advice; it is the engineering posture that follows from our own guardrails
plus what the page returns.
