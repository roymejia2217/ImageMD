"""Pure orchestration for collecting and comparing media date candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.application.date_decision import (
    DateDecision,
    DateDecisionPlanner,
    TemporalPolicy,
)
from src.domain.temporal import DateCandidate


class FilenameCandidateExtractor(Protocol):
    """Port for filename evidence extraction."""

    def extract_candidate(
        self, filename: str, *, confidence: int
    ) -> DateCandidate | None: ...


class MetadataCandidateReader(Protocol):
    """Port for reading one metadata evidence candidate."""

    def get_metadata_candidate(
        self,
        filepath: str,
        *,
        standard_confidence: int,
        deep_scan_confidence: int,
    ) -> DateCandidate | None: ...


@dataclass(frozen=True, slots=True)
class ScanPolicy:
    """Explicit confidence values used by the candidate-producing adapters."""

    filename_confidence: int
    standard_metadata_confidence: int
    deep_scan_confidence: int

    def __post_init__(self) -> None:
        for name, value in (
            ("filename_confidence", self.filename_confidence),
            ("standard_metadata_confidence", self.standard_metadata_confidence),
            ("deep_scan_confidence", self.deep_scan_confidence),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value <= 100
            ):
                raise ValueError(f"{name} must be an integer between 0 and 100")


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Candidates observed during a scan and the planner's resulting decision."""

    preferred_candidate: DateCandidate | None
    observed_candidate: DateCandidate | None
    decision: DateDecision


class MediaScanService:
    """Collect filename and metadata candidates, then delegate the decision."""

    def __init__(
        self,
        extractor: FilenameCandidateExtractor,
        metadata_reader: MetadataCandidateReader,
        temporal_policy: TemporalPolicy,
        scan_policy: ScanPolicy,
    ) -> None:
        self._extractor = extractor
        self._metadata_reader = metadata_reader
        self._planner = DateDecisionPlanner(temporal_policy)
        self._scan_policy = scan_policy

    def scan(self, filename: str, filepath: str) -> ScanResult:
        """Read each candidate once and make a non-destructive date decision."""

        preferred = self._extractor.extract_candidate(
            filename, confidence=self._scan_policy.filename_confidence
        )
        observed = self._metadata_reader.get_metadata_candidate(
            filepath,
            standard_confidence=self._scan_policy.standard_metadata_confidence,
            deep_scan_confidence=self._scan_policy.deep_scan_confidence,
        )
        decision = self._planner.plan(preferred, observed)
        return ScanResult(preferred, observed, decision)
