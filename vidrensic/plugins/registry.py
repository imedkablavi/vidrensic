from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from vidrensic.plugins.base import DetectionResult, FormatPlugin
from vidrensic.plugins.capabilities import FormatDescriptor


@dataclass(frozen=True)
class DetectionReport:
    source: Path
    results: tuple[DetectionResult, ...]
    minimum_confidence: float
    minimum_margin: float

    @property
    def best(self) -> DetectionResult:
        if not self.results:
            raise LookupError("no detection results")
        return self.results[0]

    @property
    def runner_up(self) -> DetectionResult | None:
        return self.results[1] if len(self.results) > 1 else None

    @property
    def margin(self) -> float:
        second = self.runner_up
        return self.best.confidence - (second.confidence if second else 0.0)

    @property
    def requires_review(self) -> bool:
        if self.best.confidence < self.minimum_confidence:
            return True
        second = self.runner_up
        return second is not None and second.confidence > 0 and self.margin < self.minimum_margin

    @property
    def reason(self) -> str:
        if self.best.confidence < self.minimum_confidence:
            return (
                f"best confidence {self.best.confidence:.2f} is below required "
                f"{self.minimum_confidence:.2f}"
            )
        if self.requires_review:
            return (
                f"top detection margin {self.margin:.2f} is below required "
                f"{self.minimum_margin:.2f}"
            )
        return "ranked detection is sufficiently separated for automatic selection"


class PluginRegistry:
    def __init__(self, plugins: Iterable[FormatPlugin] = ()):
        self._plugins: dict[str, FormatPlugin] = {}
        for plugin in plugins:
            self.register(plugin)

    def register(self, plugin: FormatPlugin) -> None:
        name = plugin.name.strip().lower()
        if not name:
            raise ValueError("plugin name cannot be empty")
        if name in self._plugins:
            raise ValueError(f"plugin already registered: {name}")
        self._plugins[name] = plugin

    def get(self, name: str) -> FormatPlugin:
        try:
            return self._plugins[name.lower()]
        except KeyError as exc:
            raise KeyError(f"unknown plugin: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._plugins))

    def descriptors(self) -> tuple[FormatDescriptor, ...]:
        return tuple(self._plugins[name].descriptor for name in self.names())

    def detect_all(self, source: Path) -> tuple[DetectionResult, ...]:
        results = [plugin.detect(source) for plugin in self._plugins.values()]
        results.sort(key=lambda item: (-item.confidence, item.plugin))
        return tuple(results)

    def detection_report(
        self,
        source: Path,
        *,
        minimum_confidence: float = 0.60,
        minimum_margin: float = 0.15,
    ) -> DetectionReport:
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between 0 and 1")
        if not 0.0 <= minimum_margin <= 1.0:
            raise ValueError("minimum_margin must be between 0 and 1")
        results = self.detect_all(source)
        if not results:
            raise LookupError("no format plugins are registered")
        return DetectionReport(
            source=Path(source).expanduser().resolve(),
            results=results,
            minimum_confidence=minimum_confidence,
            minimum_margin=minimum_margin,
        )

    def detect_best(self, source: Path):
        """Compatibility helper returning the highest-ranked result and plugin.

        New forensic workflows should prefer `detection_report()` so close or
        low-confidence results are not silently treated as a certain format.
        """

        report = self.detection_report(source, minimum_confidence=0.0, minimum_margin=0.0)
        result = report.best
        return result, self.get(result.plugin)
