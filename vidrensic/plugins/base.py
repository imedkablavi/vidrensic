from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from vidrensic.plugins.capabilities import FormatDescriptor


@dataclass(frozen=True)
class DetectionResult:
    plugin: str
    confidence: float
    reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class RecordingBoundary:
    label: str
    timestamp: datetime
    start_fragments: tuple[int, ...]
    data_offset: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class FormatPlugin(Protocol):
    name: str
    display_name: str
    descriptor: FormatDescriptor

    def detect(self, source: Path) -> DetectionResult: ...

    def scan_date(
        self,
        source: Path,
        target_date: date,
        *,
        data_offset: int = 0,
    ) -> list[RecordingBoundary]: ...
