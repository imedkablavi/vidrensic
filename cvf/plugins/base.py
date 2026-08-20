from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class DetectionResult:
    plugin: str
    confidence: float
    reasons: tuple[str, ...]


class ForensicPlugin(Protocol):
    name: str

    def detect(self, source: Path) -> DetectionResult:
        ...

    def scan(self, source: Path, *, output: Path) -> object:
        ...
