"""Deterministic compliance engine.

PRD §2.4 is normative: everything in here *decides*. No model imports, no I/O,
no randomness — pure functions over typed inputs so every verdict is reproducible
and 100%-branch testable. If an AI output ever needs to cross into this package,
that is a defect (tendercraft-PRD.md §2.4).
"""
