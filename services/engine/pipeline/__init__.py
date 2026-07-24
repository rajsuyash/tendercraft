"""AI pipeline components (Extractor, Retriever, Drafter, Matcher, Score).

Every component: prompt file + allowlisted output schema + confidence field + retry cap +
timeout + deterministic fallback. Model output is schema-validated before use; on failure
it falls back (queue for human), never crashes and never invents (G-5/G-6).
"""
