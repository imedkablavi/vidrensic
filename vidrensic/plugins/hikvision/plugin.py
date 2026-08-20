from __future__ import annotations

from datetime import date
from pathlib import Path

from vidrensic.plugins.base import DetectionResult, RecordingBoundary
from vidrensic.plugins.capabilities import (
    FailureMode,
    FormatDescriptor,
    FormatOperation,
    RecoveryStrategy,
    StorageTopology,
    SupportLevel,
)
from vidrensic.plugins.hikvision.master import find_master_candidates


class HikvisionPlugin:
    name = "hikvision"
    display_name = "Hikvision proprietary DVR storage"
    descriptor = FormatDescriptor(
        family_id="hikvision",
        display_name="Hikvision proprietary DVR storage",
        support_level=SupportLevel.PROFILE,
        topology=StorageTopology.PROPRIETARY_FILESYSTEM,
        operations=(FormatOperation.DETECT, FormatOperation.PROFILE),
        aliases=("HIKVISION@HANGZHOU", "HIKBTREE", "HIK proprietary DVR filesystem"),
        vendor_hints=("Hikvision-family recorders and firmware variants",),
        codecs=("raw H.264 commonly", "firmware-dependent video variants"),
        timestamp_kinds=("HIKBTREE/data-block timestamps", "system log timestamps"),
        strategies=(
            RecoveryStrategy.INDEX_GUIDED,
            RecoveryStrategy.TIMESTAMP_GUIDED,
            RecoveryStrategy.SIGNATURE_CARVE,
        ),
        failure_modes=(FailureMode.UNKNOWN_VENDOR_VARIANT,),
        notes=(
            "0.4-alpha implements dynamic Master Sector profiling, not production HIKBTREE recovery.",
            "HIKBTREE entry/page layouts differ across firmware and require variant-specific validation.",
            "Generic Annex-B carving can still provide stream-level investigative recovery when index parsing is unavailable.",
        ),
        metadata={"next_stage": "validated HIKBTREE/data-block parser"},
    )

    def detect(self, source: Path) -> DetectionResult:
        try:
            candidates = find_master_candidates(source)
        except (OSError, PermissionError, ValueError) as exc:
            return DetectionResult(self.name, 0.0, (f"safe profile failed: {type(exc).__name__}",))
        if not candidates:
            return DetectionResult(
                self.name,
                0.0,
                ("HIKVISION@HANGZHOU master signature not found in bounded search",),
            )
        best = candidates[0]
        confidence = min(0.99, 0.55 + 0.44 * best.plausibility_score)
        return DetectionResult(
            plugin=self.name,
            confidence=confidence,
            reasons=(
                f"master-sector candidates={len(candidates)}",
                f"best candidate offset=0x{best.offset:X}",
                f"best master plausibility={best.plausibility_score:.2f}",
                *best.reasons[:5],
            ),
            metadata={
                "master_candidates": [candidate.to_dict() for candidate in candidates],
                "support_stage": "PROFILE",
            },
        )

    def scan_date(
        self,
        source: Path,
        target_date: date,
        *,
        data_offset: int = 0,
    ) -> list[RecordingBoundary]:
        return []
