-- The vendor's own website, on the profile.
--
-- Two jobs. It is a fact a bid manager wants on the profile page beside the legal identity, and
-- it is the best available source of the vendor's PRODUCT VOCABULARY — the words a tender title
-- would actually use. A capability statement is written in the language of a company describing
-- itself ("expertise in elevator / crane / oil industry"); a product page is written in the
-- language of the thing ("Wire Rope · Crane Rope · Mining Rope · Elevator Rope"), which is the
-- language a procurement portal publishes in.
--
-- It is READ ONLY WHEN THE VENDOR ASKS for keyword suggestions, never crawled on a schedule:
-- G-10's crawl discipline governs portals we do not own, and the same restraint applies to a
-- customer's site. Fetching happens through `app/knowledge.py::fetch_url_text`, which is the
-- SSRF-hardened path (every hop resolved, private ranges refused, manual redirects, byte cap) —
-- a second fetcher would be a second place to get that wrong.

alter table public.vendor_profiles
  add column if not exists website_url text;

comment on column public.vendor_profiles.website_url is
  'Vendor''s public website. Read on demand for keyword suggestions; never crawled on a '
  'schedule. Fetched only via app/knowledge.py::fetch_url_text (SSRF-hardened).';
