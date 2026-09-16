"""Map an already-planned scan to UI-neutral presentation state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.application.date_decision import DecisionKind
from src.application.scan_media import ScanResult


class ScanPresentationKind(str, Enum):
    CORRUPT = "corrupt"
    MATCH = "match"
    MISMATCH = "mismatch"
    NO_METADATA = "no_metadata"
    REVIEW_REQUIRED = "review_required"
    NO_DATE = "no_date"


@dataclass(frozen=True, slots=True)
class ScanPresentation:
    kind: ScanPresentationKind
    action_needed: bool
    needs_repair: bool


def present_scan(scan: ScanResult, *, is_corrupted: bool) -> ScanPresentation:
    """Expose only auto-applicable actions; review never enters an auto-write queue."""
    if is_corrupted:
        return ScanPresentation(ScanPresentationKind.CORRUPT, True, True)
    if scan.decision.kind is DecisionKind.PROPOSE_UPDATE:
        kind = (
            ScanPresentationKind.NO_METADATA
            if scan.observed_candidate is None
            else ScanPresentationKind.MISMATCH
        )
        return ScanPresentation(kind, True, False)
    if scan.decision.kind is DecisionKind.REQUIRE_REVIEW:
        return ScanPresentation(ScanPresentationKind.REVIEW_REQUIRED, False, False)
    if (
        scan.decision.kind is DecisionKind.NO_ACTION
        and scan.preferred_candidate is not None
        and scan.observed_candidate is not None
    ):
        return ScanPresentation(ScanPresentationKind.MATCH, False, False)
    return ScanPresentation(ScanPresentationKind.NO_DATE, False, False)
