from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json

from vidrensic.acquisition.linux import inspect_source, require_safe_source
from vidrensic.plugins.defaults import default_plugin_registry
from vidrensic.profiler.hitmap import scan_signature_hitmap
from vidrensic.profiler.source import profile_source
from vidrensic.profiler.storage import profile_storage


@dataclass(frozen=True)
class TriageReport:
    source: Path
    source_info: dict[str, Any]
    storage: dict[str, Any]
    sample_profile: dict[str, Any]
    hitmap: dict[str, Any]
    format_detection: dict[str, Any]
    recommended_actions: tuple[str, ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "source": str(self.source),
            "source_info": self.source_info,
            "storage": self.storage,
            "sample_profile": self.sample_profile,
            "hitmap": self.hitmap,
            "format_detection": self.format_detection,
            "recommended_actions": list(self.recommended_actions),
            "notes": list(self.notes),
        }

    def write_json(self, output: Path) -> Path:
        output = output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_suffix(output.suffix + ".tmp")
        temp.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(output)
        return output


def _source_info_dict(source: Path) -> dict[str, Any]:
    info = inspect_source(source)
    result = asdict(info)
    result["path"] = str(info.path)
    result["mounted_at"] = list(info.mounted_at)
    result["safe_for_forensic_read"] = info.safe_for_forensic_read
    return result


def _detection_dict(report) -> dict[str, Any]:
    return {
        "requires_review": report.requires_review,
        "reason": report.reason,
        "margin": report.margin,
        "minimum_confidence": report.minimum_confidence,
        "minimum_margin": report.minimum_margin,
        "results": [
            {
                "plugin": result.plugin,
                "confidence": result.confidence,
                "reasons": list(result.reasons),
                "metadata": result.metadata,
            }
            for result in report.results
        ],
    }


def _recommendations(detection, storage, hitmap) -> tuple[str, ...]:
    actions: list[str] = []
    if detection.requires_review:
        actions.append(
            "do not auto-select a proprietary parser; review ranked family evidence and expand profiling if needed"
        )
    else:
        family = detection.best.plugin
        if family == "wfs":
            actions.extend(
                [
                    "profile WFS fragment alignment/data-area evidence before assuming an absolute data offset",
                    "when the WFS layout is validated, scan the target date and reconstruct simultaneous candidates",
                ]
            )
        elif family == "dhav":
            actions.extend(
                [
                    "map DHAV physical frame density and channel/timestamp ranges",
                    "demultiplex validated DHAV records while preserving physical-order evidence",
                ]
            )
        elif family == "hikvision":
            actions.extend(
                [
                    "retain the Master Sector candidate/profile evidence",
                    "do not claim HIKBTREE recording recovery until a compatible firmware/index variant is validated",
                    "use stream-level Annex-B evidence as an investigative fallback when appropriate",
                ]
            )
        elif family in {"annexb", "mpegps"}:
            actions.extend(
                [
                    "treat the detected stream/container as a payload layer, not proof of the recorder filesystem/vendor",
                    "search for surrounding proprietary index/timestamp/channel metadata before assigning wall-clock time",
                ]
            )

    filesystems = storage.get("filesystems", [])
    if filesystems:
        actions.append(
            "inspect known filesystem regions as metadata/file candidates but keep unpartitioned/proprietary video areas in scope"
        )

    strong_hits = [
        row
        for row in hitmap.get("signatures", [])
        if row.get("evidence_strength") == "strong-structural-marker" and row.get("count", 0) > 0
    ]
    if strong_hits:
        actions.append(
            "correlate strong structural-marker offsets with partition/data-area boundaries before selecting a parser"
        )

    if not actions:
        actions.extend(
            [
                "run a wider/full physical hit map and collect a compact profiler package for the unknown recorder",
                "look for repeated block geometry, channel fields, timestamps and codec parameter sets without modifying evidence",
            ]
        )
    return tuple(actions)


def triage_source(
    source: Path,
    *,
    sample_size: int = 4 * 1024 * 1024,
    sample_count: int = 5,
    hitmap_size: int | None = 512 * 1024 * 1024,
    hitmap_chunk_size: int = 16 * 1024 * 1024,
    max_offsets_per_signature: int = 128,
    minimum_confidence: float = 0.60,
    minimum_margin: float = 0.15,
) -> TriageReport:
    """Run safe read-only first-pass triage for an unknown DVR/NVR source.

    `hitmap_size=None` requests a complete physical signature pass. The default
    is intentionally bounded so first-pass triage remains predictable on large
    evidence disks.
    """

    info = require_safe_source(source)
    source_info = _source_info_dict(info.path)
    storage_report = profile_storage(info.path)
    samples = profile_source(
        info.path,
        sample_size=sample_size,
        sample_count=sample_count,
    )
    hitmap = scan_signature_hitmap(
        info.path,
        range_start=0,
        range_size=hitmap_size,
        chunk_size=hitmap_chunk_size,
        max_offsets_per_signature=max_offsets_per_signature,
    )
    registry = default_plugin_registry()
    detection = registry.detection_report(
        info.path,
        minimum_confidence=minimum_confidence,
        minimum_margin=minimum_margin,
    )

    storage_dict = storage_report.to_dict()
    hitmap_dict = hitmap.to_dict()
    return TriageReport(
        source=info.path,
        source_info=source_info,
        storage=storage_dict,
        sample_profile=samples.to_dict(),
        hitmap=hitmap_dict,
        format_detection=_detection_dict(detection),
        recommended_actions=_recommendations(detection, storage_dict, hitmap_dict),
        notes=(
            "first-pass triage is forensic metadata generation; it does not modify or repair the source",
            "the default hit map is bounded to the configured leading range and is not a complete-disk scan",
            "a family ranking is a parser-selection aid, not a substitute for variant validation",
        ),
    )
