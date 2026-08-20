from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class EvidenceStatus(StrEnum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class ArtifactKind(StrEnum):
    SOURCE = "source"
    ACQUISITION = "acquisition"
    NATIVE = "native"
    REVIEW_PROXY = "review_proxy"
    REPORT = "report"
    METADATA = "metadata"


@dataclass(frozen=True)
class HashSet:
    sha256: str
    sha512: str | None = None


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    kind: ArtifactKind
    path: Path
    size_bytes: int
    hashes: HashSet | None = None
    derived_from: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QCDecision:
    status: EvidenceStatus
    reasons: tuple[str, ...] = ()
    measurements: dict[str, Any] = field(default_factory=dict)

    @property
    def is_final_pass(self) -> bool:
        return self.status is EvidenceStatus.PASS and not self.reasons
