from __future__ import annotations

from datetime import date
from pathlib import Path

from vidrensic.plugins.base import DetectionResult, RecordingBoundary
from vidrensic.plugins.wfs.codec import SYNC, fd_timestamp, packet_info
from vidrensic.plugins.wfs.scanner import scan_recording_starts


class WFSPlugin:
    name = "wfs"
    display_name = "WFS surveillance storage (observed 0.5 profile)"

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

        with source.open("rb", buffering=0) as fh:
            while scanned < sample_limit:
                chunk = fh.read(min(chunk_size, sample_limit - scanned))
                if not chunk:
                    break
                data = carry + chunk
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
                if plausible_timestamps >= 8:
                    break

        if plausible_timestamps >= 8:
            confidence = 0.95
        elif plausible_timestamps >= 3:
            confidence = 0.80
        elif plausible_timestamps >= 1 and valid >= 2:
            confidence = 0.55
        elif valid:
            confidence = 0.25
        else:
            confidence = 0.0

        reasons = (
            f"valid FD-like records={valid}",
            f"plausible WFS timestamps={plausible_timestamps}",
            f"sampled bytes={scanned}",
        )
        return DetectionResult(
            plugin=self.name,
            confidence=confidence,
            reasons=reasons,
            metadata={
                "profile": "observed-wfs-0.5",
                "sampled_bytes": scanned,
                "valid_fd_records": valid,
                "timestamp_records": plausible_timestamps,
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
