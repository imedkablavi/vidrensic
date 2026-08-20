from __future__ import annotations

from datetime import date
from pathlib import Path

from vidrensic.plugins.base import DetectionResult, RecordingBoundary
from vidrensic.plugins.capabilities import (
    FailureMode,
    FormatDescriptor,
    RecoveryStrategy,
    StorageTopology,
    SupportLevel,
)
from vidrensic.plugins.wfs.codec import SYNC, fd_timestamp, packet_info
from vidrensic.plugins.wfs.scanner import scan_recording_starts


class WFSPlugin:
    name = "wfs"
    display_name = "WFS surveillance storage"
    descriptor = FormatDescriptor(
        family_id="wfs",
        display_name="WFS surveillance storage",
        support_level=SupportLevel.RECONSTRUCT,
        topology=StorageTopology.PROPRIETARY_FILESYSTEM,
        aliases=("WFS 0.4", "WFS 0.5", "WFH-family investigative lead"),
        codecs=("H.264 variants", "H.265/HEVC variants"),
        timestamp_kinds=("observed WFS packed timestamp",),
        strategies=(
            RecoveryStrategy.TIMESTAMP_GUIDED,
            RecoveryStrategy.FRAGMENT_CHAIN,
            RecoveryStrategy.CHANNEL_DEMUX,
            RecoveryStrategy.SIGNATURE_CARVE,
            RecoveryStrategy.STREAM_COPY,
        ),
        failure_modes=(
            FailureMode.MISSING_OR_CORRUPT_INDEX,
            FailureMode.DELETED_RECORDING,
            FailureMode.CIRCULAR_WRAP,
            FailureMode.INTERLEAVED_CAMERAS,
            FailureMode.CHANNEL_SLOT_DRIFT,
            FailureMode.FRAGMENTATION,
            FailureMode.BAD_SECTORS,
            FailureMode.TRUNCATED_RECORD,
            FailureMode.TIMESTAMP_GAPS,
            FailureMode.VARIABLE_OR_WRONG_FPS,
            FailureMode.WRONG_PLAYBACK_DURATION,
            FailureMode.UNKNOWN_VENDOR_VARIANT,
        ),
        notes=(
            "Current reconstruction is validated against the observed WFS framing used by the project case corpus.",
            "WFS/firmware variants must be profiled before the engine claims structural compatibility.",
            "Global weighted fragment-graph solving and frame-level partial-overwrite salvage remain future stages.",
        ),
        metadata={"current_profile": "observed-wfs-0.5-framing"},
    )

    def detect(self, source: Path) -> DetectionResult:
        source = source.expanduser().resolve()
        if not source.exists():
            return DetectionResult(self.name, 0.0, ("source does not exist",))

        sample_limit = 128 * 1024 * 1024
        chunk_size = 4 * 1024 * 1024
        valid = 0
        plausible_timestamps = 0
        scanned = 0
        carry = b""
        ascii_versions: set[str] = set()

        with source.open("rb", buffering=0) as fh:
            while scanned < sample_limit:
                chunk = fh.read(min(chunk_size, sample_limit - scanned))
                if not chunk:
                    break
                data = carry + chunk
                if b"WFS 0.4" in data:
                    ascii_versions.add("0.4")
                if b"WFS 0.5" in data:
                    ascii_versions.add("0.5")
                pos = 0
                while True:
                    pos = data.find(SYNC + b"\xfd", pos)
                    if pos < 0:
                        break
                    info = packet_info(data, pos)
                    if info is not None:
                        valid += 1
                        timestamp = fd_timestamp(data[pos : pos + 16])
                        if timestamp is not None:
                            plausible_timestamps += 1
                    pos += 4
                carry = data[-32:]
                scanned += len(chunk)
                if plausible_timestamps >= 8 and ascii_versions:
                    break

        if plausible_timestamps >= 8:
            confidence = 0.95
        elif plausible_timestamps >= 3:
            confidence = 0.80
        elif plausible_timestamps >= 1 and valid >= 2:
            confidence = 0.55
        elif valid:
            confidence = 0.25
        elif ascii_versions:
            confidence = 0.20
        else:
            confidence = 0.0

        reasons = (
            f"valid FD-like records={valid}",
            f"plausible WFS timestamps={plausible_timestamps}",
            f"ASCII version markers={','.join(sorted(ascii_versions)) or 'none'}",
            f"sampled bytes={scanned}",
        )
        return DetectionResult(
            plugin=self.name,
            confidence=confidence,
            reasons=reasons,
            metadata={
                "profile": "observed-wfs-framing",
                "sampled_bytes": scanned,
                "valid_fd_records": valid,
                "timestamp_records": plausible_timestamps,
                "ascii_versions": sorted(ascii_versions),
            },
        )

    def scan_date(
        self,
        source: Path,
        target_date: date,
        *,
        data_offset: int = 0,
    ) -> list[RecordingBoundary]:
        return scan_recording_starts(source, target_date, data_offset=data_offset)
