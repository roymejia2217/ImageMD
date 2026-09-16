"""Policy-driven planning of metadata date changes.

This use case intentionally produces a decision only.  It has no filesystem or
media-library dependency and therefore cannot mutate a file while scanning it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from zoneinfo import ZoneInfo

from src.domain.temporal import (
    CandidateComparison,
    DateCandidate,
    DateSource,
    LocalTimeResolution,
    compare_candidates,
)


class DecisionKind(str, Enum):
    NO_ACTION = "no_action"
    PROPOSE_UPDATE = "propose_update"
    REQUIRE_REVIEW = "require_review"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True, slots=True)
class TemporalPolicy:
    """Explicit settings that govern automatic date-change proposals."""

    timezone: ZoneInfo
    tolerance_seconds: int
    automatic_write_confidence: int
    local_time_resolution: LocalTimeResolution = LocalTimeResolution.REJECT

    def __post_init__(self) -> None:
        if self.tolerance_seconds < 0:
            raise ValueError("tolerance_seconds must be non-negative")
        if not 0 <= self.automatic_write_confidence <= 100:
            raise ValueError("automatic_write_confidence must be between 0 and 100")


@dataclass(frozen=True, slots=True)
class DateDecision:
    kind: DecisionKind
    target: DateCandidate | None
    reason: str
    comparison: CandidateComparison | None = None


class DateDecisionPlanner:
    """Turn date candidates into an explicit, non-destructive change decision."""

    def __init__(self, policy: TemporalPolicy) -> None:
        self._policy = policy

    def plan(
        self,
        preferred: DateCandidate | None,
        observed: DateCandidate | None,
    ) -> DateDecision:
        """Plan a date change; low-confidence and incomparable data never auto-writes."""

        if preferred is None and observed is None:
            return DateDecision(
                DecisionKind.INSUFFICIENT_EVIDENCE,
                None,
                "no date candidate was found",
            )
        if preferred is None:
            return DateDecision(
                DecisionKind.NO_ACTION,
                None,
                "only observed metadata is available",
            )
        if observed is None:
            return self._proposal_for_unobserved(preferred)

        comparison = compare_candidates(
            preferred,
            observed,
            tolerance_seconds=self._policy.tolerance_seconds,
            zone=self._policy.timezone,
            resolution=self._policy.local_time_resolution,
        )
        if comparison is CandidateComparison.MATCH:
            return DateDecision(
                DecisionKind.NO_ACTION, None, "timestamps match", comparison
            )
        if comparison is CandidateComparison.INCOMPARABLE:
            return DateDecision(
                DecisionKind.REQUIRE_REVIEW,
                preferred,
                "timestamps cannot be compared under the current timezone policy",
                comparison,
            )
        if DateSource.DEEP_SCAN in (preferred.source, observed.source):
            return DateDecision(
                DecisionKind.REQUIRE_REVIEW,
                preferred,
                "a deep-scan candidate cannot authorize an automatic metadata change",
                comparison,
            )
        if not self._is_eligible_for_automatic_write(preferred):
            return DateDecision(
                DecisionKind.REQUIRE_REVIEW,
                preferred,
                "preferred candidate does not meet automatic-write policy",
                comparison,
            )
        return DateDecision(
            DecisionKind.PROPOSE_UPDATE,
            preferred,
            "preferred candidate differs from observed metadata",
            comparison,
        )

    def _proposal_for_unobserved(self, preferred: DateCandidate) -> DateDecision:
        if self._is_eligible_for_automatic_write(preferred):
            return DateDecision(
                DecisionKind.PROPOSE_UPDATE,
                preferred,
                "no metadata date is present",
            )
        return DateDecision(
            DecisionKind.REQUIRE_REVIEW,
            preferred,
            "no metadata date is present but source confidence requires review",
        )

    def _is_eligible_for_automatic_write(self, candidate: DateCandidate) -> bool:
        # A deep binary scan is intentionally never sufficient for automatic mutation.
        return (
            candidate.source is not DateSource.DEEP_SCAN
            and candidate.confidence >= self._policy.automatic_write_confidence
        )
