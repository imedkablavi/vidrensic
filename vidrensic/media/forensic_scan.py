from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
import stat
from typing import Any

from vidrensic.core.hashing import forensic_hashes_stable
from vidrensic.core.models import EvidenceStatus
from vidrensic.media.decoder_regions import DecoderRegionReport, analyze_decoder_error_regions
from vidrensic.media.inventory import MediaInventoryReport, inspect_media
from vidrensic.media.timeline import MediaTimelineReport, analyze_media_timeline


SCAN_SCHEMA_VERSION = 1
MAX_FINDINGS = 128
FPS_DISAGREEMENT_REVIEW_FRACTION = 0.05
MIN_REASONABLE_FPS = 1.0
MAX_REASONABLE_FPS = 120.0


@dataclass(frozen=True)
class ScanFinding:
    code: str
    severity: str
    message: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ForensicScanReport:
    artifact: Path
    size_bytes: int
    sha256_before: str
    sha512_before: str | None
    sha256_after: str
    sha512_after: str | None
    started_utc: str
    completed_utc: str
    profile: str
    inventory: MediaInventoryReport
    findings: tuple[ScanFinding, ...]
    qc: dict[str, Any] | None
    timeline: dict[str, Any] | None
    decoder_regions: dict[str, Any] | None
    status: EvidenceStatus

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCAN_SCHEMA_VERSION,
            "artifact": str(self.artifact),
            "size_bytes": self.size_bytes,
            "hashes": {
                "sha256_before": self.sha256_before,
                "sha512_before": self.sha512_before,
                "sha256_after": self.sha256_after,
                "sha512_after": self.sha512_after,
                "stable": self.sha256_before == self.sha256_after
                and self.sha512_before == self.sha512_after,
            },
            "started_utc": self.started_utc,
            "completed_utc": self.completed_utc,
            "profile": self.profile,
            "status": self.status.value,
            "findings": [finding.to_dict() for finding in self.findings],
            "inventory": self.inventory.to_dict(),
            "qc": self.qc,
            "timeline": self.timeline,
            "decoder_regions": self.decoder_regions,
            "limitations": [
                "Anomalies indicate conditions requiring review; they do not prove intentional tampering.",
                "A PASS requires the selected deep profile to complete without findings, with full decode and complete timeline evidence.",
                "Stable hashing detects ordinary concurrent mutation/replacement but is not filesystem snapshotting against a privileged adversary.",
            ],
        }

    def write_json(self, output: Path, *, replace: bool = False) -> Path:
        from vidrensic.core.private_io import atomic_write_private_json

        return atomic_write_private_json(output, self.to_dict(), allow_replace=replace)


def _regular_file(path: Path) -> Path:
    candidate = path.expanduser()
    if candidate.is_symlink():
        raise ValueError("forensic scan target may not be a symlink")
    resolved = candidate.resolve(strict=True)
    mode = resolved.stat().st_mode
    if not stat.S_ISREG(mode):
        raise ValueError("forensic scan target must be a regular file")
    return resolved


def _finding(
    findings: list[ScanFinding],
    code: str,
    severity: str,
    message: str,
    evidence: dict[str, Any] | None = None,
) -> None:
    if len(findings) >= MAX_FINDINGS:
        return
    findings.append(
        ScanFinding(
            code=code,
            severity=severity,
            message=message,
            evidence=evidence or {},
        )
    )


def _analyze_inventory(report: MediaInventoryReport, findings: list[ScanFinding]) -> None:
    if report.size_bytes <= 0:
        _finding(findings, "EMPTY_ARTIFACT", "FAIL", "media file is empty")
    if report.video_codec is None:
        _finding(findings, "NO_VIDEO_STREAM", "FAIL", "no video stream was detected")
        return
    if report.duration is not None if False else False:
        pass

    video_streams = [stream for stream in report.streams if stream.codec_type == "video"]
    audio_streams = [stream for stream in report.streams if stream.codec_type == "audio"]
    if len(video_streams) > 1:
        _finding(
            findings,
            "MULTIPLE_VIDEO_STREAMS",
            "REVIEW",
            "multiple video streams were found; review stream selection and recorder layout",
            {"video_stream_count": len(video_streams)},
        )
    if not audio_streams:
        _finding(
            findings,
            "NO_AUDIO_STREAM",
            "INFO",
            "no audio stream was detected",
        )

    for stream in video_streams:
        if stream.width is None or stream.height is None:
            _finding(
                findings,
                "MISSING_VIDEO_DIMENSIONS",
                "REVIEW",
                "video stream dimensions are unavailable",
                {"stream_index": stream.index},
            )
        elif stream.width <= 0 or stream.height <= 0:
            _finding(
                findings,
                "INVALID_VIDEO_DIMENSIONS",
                "FAIL",
                "video stream has non-positive dimensions",
                {
                    "stream_index": stream.index,
                    "width": stream.width,
                    "height": stream.height,
                },
            )

        avg = stream.avg_frame_rate
        real = stream.r_frame_rate
        if avg is not None and not (MIN_REASONABLE_FPS <= avg <= MAX_REASONABLE_FPS):
            _finding(
                findings,
                "UNUSUAL_AVERAGE_FPS",
                "REVIEW",
                "average frame rate falls outside the conservative review range",
                {"stream_index": stream.index, "avg_frame_rate": avg},
            )
        if real is not None and not (MIN_REASONABLE_FPS <= real <= MAX_REASONABLE_FPS):
            _finding(
                findings,
                "UNUSUAL_R_FPS",
                "REVIEW",
                "reference frame rate falls outside the conservative review range",
                {"stream_index": stream.index, "r_frame_rate": real},
            )
        if avg is not None and real is not None:
            denominator = max(abs(avg), abs(real), 1e-9)
            disagreement = abs(avg - real) / denominator
            if disagreement > FPS_DISAGREEMENT_REVIEW_FRACTION:
                _finding(
                    findings,
                    "FRAME_RATE_DISAGREEMENT",
                    "REVIEW",
                    "average and reference frame rates materially disagree",
                    {
                        "stream_index": stream.index,
                        "avg_frame_rate": avg,
                        "r_frame_rate": real,
                        "relative_difference": disagreement,
                    },
                )

    dimensions = {
        (stream.width, stream.height)
        for stream in video_streams
        if stream.width is not None and stream.height is not None
    }
    if len(dimensions) > 1:
        _finding(
            findings,
            "INCONSISTENT_VIDEO_DIMENSIONS",
            "REVIEW",
            "video streams use different dimensions",
            {"dimensions": sorted(dimensions)},
        )


def _analyze_timeline(report: MediaTimelineReport, findings: list[ScanFinding]) -> None:
    if report.truncated:
        _finding(
            findings,
            "TIMELINE_TRUNCATED",
            "REVIEW",
            "timeline analysis reached its configured evidence bound",
            {"frame_count": report.frame_count, "keyframe_count": report.keyframe_count},
        )
    if report.pts_non_monotonic:
        _finding(findings, "PTS_NON_MONOTONIC", "REVIEW", "presentation timestamps are non-monotonic")
    if report.dts_non_monotonic:
        _finding(findings, "DTS_NON_MONOTONIC", "REVIEW", "decode timestamps are non-monotonic")
    if report.duplicate_pts:
        _finding(findings, "DUPLICATE_PTS", "REVIEW", "duplicate presentation timestamps were detected")
    if report.large_gaps:
        _finding(findings, "LARGE_TIMESTAMP_GAPS", "REVIEW", "large timestamp gaps were detected")
    if report.duration_delta_seconds is not None and abs(report.duration_delta_seconds) > 1.0:
        _finding(
            findings,
            "DURATION_VS_FRAME_TIMESTAMPS",
            "REVIEW",
            "container duration materially differs from observed frame timestamps",
            {"delta_seconds": report.duration_delta_seconds},
        )


def _analyze_decoder_regions(report: DecoderRegionReport, findings: list[ScanFinding]) -> None:
    if report.failed_window_count:
        _finding(
            findings,
            "DECODER_ERROR_WINDOWS",
            "FAIL",
            "sampled decode windows contain decoder failures",
            {
                "failed_window_count": report.failed_window_count,
                "window_count": report.window_count,
            },
        )
    if not report.sampling_complete:
        _finding(
            findings,
            "DECODER_SAMPLING_INCOMPLETE",
            "REVIEW",
            "decoder-error sampling did not cover the configured evidence set completely",
            {"coverage_fraction": report.coverage_fraction},
        )


def _derive_status(findings: list[ScanFinding], *, profile: str, qc: dict[str, Any] | None, timeline: dict[str, Any] | None, decoder_regions: dict[str, Any] | None, hash_stable: bool) -> EvidenceStatus:
    if not hash_stable:
        return EvidenceStatus.FAIL
    if any(item.severity == "FAIL" for item in findings):
        return EvidenceStatus.FAIL
    if profile == "deep":
        if qc is None or qc.get("status") != EvidenceStatus.PASS.value:
            return EvidenceStatus.REVIEW
        if timeline is None:
            return EvidenceStatus.REVIEW
        if timeline.get("truncated"):
            return EvidenceStatus.REVIEW
        if any(
            bool(timeline.get(key))
            for key in ("pts_non_monotonic", "dts_non_monotonic", "duplicate_pts", "large_gaps")
        ):
            return EvidenceStatus.REVIEW
        if decoder_regions is not None:
            if decoder_regions.get("failed_window_count", 0) or not decoder_regions.get("sampling_complete", False):
                return EvidenceStatus.REVIEW
        if any(item.severity == "REVIEW" for item in findings):
            return EvidenceStatus.REVIEW
        return EvidenceStatus.PASS
    if profile in {"standard", "quick"}:
        return EvidenceStatus.REVIEW if findings or qc is None else EvidenceStatus.REVIEW
    return EvidenceStatus.UNKNOWN


def run_forensic_scan(
    path: Path,
    *,
    profile: str = "standard",
    expected_duration: float | None = None,
    timeout: float | None = None,
    decoder_errors: bool = False,
    decoder_window_seconds: float = 4.0,
    decoder_max_windows: int = 512,
) -> ForensicScanReport:
    """Run a bounded, conservative composite scan over one video artifact."""

    if profile not in {"quick", "standard", "deep"}:
        raise ValueError("profile must be one of: quick, standard, deep")
    if expected_duration is not None and expected_duration <= 0:
        raise ValueError("expected_duration must be positive")
    if timeout is not None and timeout <= 0:
        raise ValueError("timeout must be positive")
    artifact = _regular_file(path)
    started = datetime.now(UTC).isoformat()
    before = forensic_hashes_stable(artifact)
    findings: list[ScanFinding] = []

    qc_mode = "fast" if profile in {"quick", "standard"} else "full"
    inventory = inspect_media(
        artifact,
        qc_mode=qc_mode,
        expected_duration=expected_duration,
        full_decode_timeout=timeout,
    )
    _analyze_inventory(inventory, findings)

    timeline_report: MediaTimelineReport | None = None
    if profile in {"standard", "deep"}:
        timeline_report = analyze_media_timeline(
            artifact,
            timeout=timeout if timeout is not None else 1800.0,
        )
        _analyze_timeline(timeline_report, findings)

    decoder_report: DecoderRegionReport | None = None
    if decoder_errors:
        decoder_report = analyze_decoder_error_regions(
            artifact,
            window_seconds=decoder_window_seconds,
            max_windows=decoder_max_windows,
            timeout_per_window=timeout if timeout is not None else 20.0,
        )
        _analyze_decoder_regions(decoder_report, findings)

    after = forensic_hashes_stable(artifact)
    hash_stable = before.sha256 == after.sha256 and before.sha512 == after.sha512
    if not hash_stable:
        _finding(
            findings,
            "ARTIFACT_CHANGED_DURING_SCAN",
            "FAIL",
            "artifact hash changed during forensic scanning; inspection evidence is invalidated",
            {"sha256_before": before.sha256, "sha256_after": after.sha256},
        )

    qc_dict = inventory.qc
    timeline_dict = None if timeline_report is None else timeline_report.to_dict()
    decoder_dict = None if decoder_report is None else decoder_report.to_dict()
    status = _derive_status(
        findings,
        profile=profile,
        qc=qc_dict,
        timeline=timeline_dict,
        decoder_regions=decoder_dict,
        hash_stable=hash_stable,
    )

    completed = datetime.now(UTC).isoformat()
    return ForensicScanReport(
        artifact=artifact,
        size_bytes=artifact.stat().st_size,
        sha256_before=before.sha256,
        sha512_before=before.sha512,
        sha256_after=after.sha256,
        sha512_after=after.sha512,
        started_utc=started,
        completed_utc=completed,
        profile=profile,
        inventory=inventory,
        findings=tuple(findings),
        qc=qc_dict,
        timeline=timeline_dict,
        decoder_regions=decoder_dict,
        status=status,
    )
