"""Explicit, lossless temporal semantics for metadata decisions.

Media names commonly contain a wall-clock time while EXIF and video metadata may
represent either local time or an instant in UTC.  A naive ``datetime`` cannot
express that distinction safely.  This module keeps it until comparison or write
time, where a policy must resolve local values deliberately.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from zoneinfo import ZoneInfo


class DateSource(str, Enum):
    """Origin of an observed or inferred timestamp."""

    FILENAME = "filename"
    EXIF = "exif"
    VIDEO_METADATA = "video_metadata"
    FILESYSTEM = "filesystem"
    DEEP_SCAN = "deep_scan"


class LocalTimeResolution(str, Enum):
    """How a DST-ambiguous wall time is converted to an instant."""

    REJECT = "reject"
    EARLIEST = "earliest"
    LATEST = "latest"


class AmbiguousLocalTimeError(ValueError):
    """Raised when a wall time maps to two instants and policy rejects it."""


class NonexistentLocalTimeError(ValueError):
    """Raised when a wall time does not exist because of a DST transition."""


class CandidateComparison(str, Enum):
    """Result of comparing two candidates at instant precision."""

    MATCH = "match"
    DIFFERENT = "different"
    INCOMPARABLE = "incomparable"


@dataclass(frozen=True, slots=True)
class DateCandidate:
    """A timestamp plus its origin, confidence, and temporal semantics.

    ``observed_at`` is aware for an instant and naive for a local wall-clock value.
    The constructor enforces that invariant so callers cannot silently strip a
    timezone as the former implementation did.
    """

    observed_at: datetime
    source: DateSource
    confidence: int
    evidence: str

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 100:
            raise ValueError("confidence must be between 0 and 100")
        if not self.evidence.strip():
            raise ValueError("evidence must not be blank")

    @property
    def is_instant(self) -> bool:
        return (
            self.observed_at.tzinfo is not None
            and self.observed_at.utcoffset() is not None
        )

    def as_instant(
        self,
        zone: ZoneInfo | None = None,
        resolution: LocalTimeResolution = LocalTimeResolution.REJECT,
    ) -> datetime:
        """Return a UTC instant without guessing an ambiguous/nonexistent local time.

        A local candidate must receive the timezone policy that gave it meaning.  A
        round trip through UTC is used to distinguish valid, ambiguous and
        nonexistent local times; assigning ``tzinfo`` alone would accept a gap.
        """

        if self.is_instant:
            return self.observed_at.astimezone(timezone.utc)
        if zone is None:
            raise ValueError("a timezone policy is required for a local timestamp")

        possibilities = _local_possibilities(self.observed_at, zone)
        if not possibilities:
            raise NonexistentLocalTimeError(
                f"{self.observed_at.isoformat()} does not exist in {zone.key}"
            )
        if len(possibilities) == 1:
            return possibilities[0]
        if resolution is LocalTimeResolution.REJECT:
            raise AmbiguousLocalTimeError(
                f"{self.observed_at.isoformat()} is ambiguous in {zone.key}"
            )
        return (
            possibilities[0]
            if resolution is LocalTimeResolution.EARLIEST
            else possibilities[-1]
        )


def _local_possibilities(local_time: datetime, zone: ZoneInfo) -> tuple[datetime, ...]:
    """Return UTC instants that round-trip to ``local_time`` in ``zone``."""

    possibilities: list[datetime] = []
    for fold in (0, 1):
        aware = local_time.replace(tzinfo=zone, fold=fold)
        instant = aware.astimezone(timezone.utc)
        round_trip = instant.astimezone(zone)
        if (
            round_trip.replace(tzinfo=None) == local_time
            and instant not in possibilities
        ):
            possibilities.append(instant)
    return tuple(sorted(possibilities))


def compare_candidates(
    first: DateCandidate,
    second: DateCandidate,
    *,
    tolerance_seconds: int,
    zone: ZoneInfo | None = None,
    resolution: LocalTimeResolution = LocalTimeResolution.REJECT,
) -> CandidateComparison:
    """Compare candidates only when both can be resolved to explicit instants."""

    if tolerance_seconds < 0:
        raise ValueError("tolerance_seconds must be non-negative")
    try:
        first_instant = first.as_instant(zone, resolution)
        second_instant = second.as_instant(zone, resolution)
    except (AmbiguousLocalTimeError, NonexistentLocalTimeError, ValueError):
        return CandidateComparison.INCOMPARABLE
    difference = abs((first_instant - second_instant).total_seconds())
    return (
        CandidateComparison.MATCH
        if difference <= tolerance_seconds
        else CandidateComparison.DIFFERENT
    )
