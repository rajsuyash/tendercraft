"""Typed inputs for the gates. Pure data — no I/O, no model, no framework."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


class CompareKind(StrEnum):
    NUMERIC = "numeric"
    DATE = "date"
    BOOLEAN = "boolean"
    QUALITATIVE = "qualitative"


class Verdict(StrEnum):
    MEETS = "meets"
    FAILS = "fails"
    NOT_STATED = "not_stated"   # never silently a fail — an extraction miss is not a defect
    MANUAL = "manual"           # qualitative: a human decides, AI only locates evidence


@dataclass(frozen=True)
class Criterion:
    id: str
    kind: str                    # "pq" | "technical"
    text: str
    max_marks: int = 0
    compare_kind: CompareKind = CompareKind.QUALITATIVE
    compare_op: str | None = None      # ">=" | "<=" | "=" | "present"
    compare_value: str | None = None


@dataclass(frozen=True)
class Response:
    criterion_id: str
    stated_value: str | None = None
    anchor_page: int | None = None


@dataclass(frozen=True)
class Score:
    bid_id: str
    criterion_id: str
    evaluator_id: str
    final_mark: Decimal


@dataclass(frozen=True)
class Consensus:
    bid_id: str
    criterion_id: str
    agreed_mark: Decimal


@dataclass(frozen=True)
class ScreeningCell:
    criterion_id: str
    verdict: Verdict
    required: str | None
    stated: str | None
    anchor_page: int | None = None


@dataclass(frozen=True)
class CriterionAggregate:
    criterion_id: str
    max_marks: int
    marks: tuple[Decimal, ...] = field(default_factory=tuple)
    consensus: Decimal | None = None

    @property
    def spread(self) -> Decimal:
        return (max(self.marks) - min(self.marks)) if len(self.marks) > 1 else Decimal(0)
