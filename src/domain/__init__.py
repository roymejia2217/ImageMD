"""Pure domain types for ImageMD.

The domain package deliberately has no dependency on GUI toolkits, media libraries,
or filesystem APIs.  This keeps decisions about timestamps and metadata provenance
testable independently from the adapters that read and write files.
"""

from .temporal import (
    AmbiguousLocalTimeError,
    CandidateComparison,
    DateCandidate,
    DateSource,
    LocalTimeResolution,
    NonexistentLocalTimeError,
    compare_candidates,
)

__all__ = [
    "AmbiguousLocalTimeError",
    "CandidateComparison",
    "DateCandidate",
    "DateSource",
    "LocalTimeResolution",
    "NonexistentLocalTimeError",
    "compare_candidates",
]
