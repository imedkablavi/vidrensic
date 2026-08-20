from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json
import subprocess

from vidrensic.core.models import EvidenceStatus, QCDecision
from vidrensic.media.probe import VideoProbe, decode_window, probe_video


@dataclass(frozen=True)
class DecodeCheckpoint:
    name: str
    position_seconds: float
    duration_seconds: float
    ok: bool
    error: str


@dataclass(frozen=True)
class MediaQCReport:
    path: Path
    mode: str
    decision: QCDecision
    probe: VideoProbe
    checkpoints: tuple[DecodeCheckpoint, ...] = ()
    full_decode_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "mode": self.mode,
            "decision": {
                "status": self.decision.status.value,
                "reasons": list(self.decision.reasons),
                "measurements": self.decision.measurements,
            },
            "probe": {
                "duration": self.probe.duration,
                "codec": self.probe.codec,
                "width": self.probe.width,
                "height": self.probe.height,
                "avg_frame_rate": self.probe.avg_frame_rate,
                "r_frame_rate": self.probe.r_frame_rate,
                "stream_count": self.probe.stream_count,
            },
            "checkpoints": [asdict(item) for item in self.checkpoints],
            "full_decode_error": self.full_decode_error,
        }

    def write_json(self, output: Path) -> Path:
        output = output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_suffix(output.suffix + ".tmp")
        temp.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(output)
        return output


def _duration_measurements(
    observed: float | None,
    expected: float | None,
) -> tuple[dict[str, Any], list[str], bool]:
    measurements: dict[str, Any] = {
        "observed_duration": observed,
        "expected_duration": expected,
        "duration_error_fraction": None,
    }
    reasons: list[str] = []
    hard_fail = False
    if expected is None:
        reasons.append("expected duration not supplied")
        return measurements, reasons, hard_fail
    if expected <= 0:
        raise ValueError("expected_duration must be positive")
    if observed is None:
        reasons.append("media duration unavailable")
        return measurements, reasons, hard_fail

    error = abs(observed - expected) / expected
    measurements["duration_error_fraction"] = error
    # Conservative defaults: >2% is a hard timing inconsistency; 0.5-2% needs review.
    if error > 0.02:
        reasons.append(f"duration differs from expected by {error:.2%}")
        hard_fail = True
    elif error > 0.005:
        reasons.append(f"duration differs from expected by {error:.2%}")
    return measurements, reasons, hard_fail


def fast_three_point_check(
    path: Path,
    *,
    expected_duration: float | None = None,
    window_seconds: float = 2.0,
    timeout_per_window: float = 20.0,
) -> MediaQCReport:
    """Decode short windows near the beginning, midpoint, and end.

    A clean result is REVIEW, not PASS, because most frames were not decoded.
    """

    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    probe = probe_video(path)
    if probe.codec is None:
        return MediaQCReport(
            path=path.resolve(),
            mode="three-point",
            decision=QCDecision(EvidenceStatus.FAIL, ("no video stream detected",)),
            probe=probe,
        )

    duration = probe.duration
    if duration is None or duration <= 0:
        positions = (0.0,)
        names = ("start",)
    else:
        end = max(0.0, duration - window_seconds - 0.25)
        positions = (min(1.0, end), duration / 2.0, end)
        names = ("start", "middle", "end")

    checkpoints: list[DecodeCheckpoint] = []
    for name, position in zip(names, positions, strict=True):
        ok, error = decode_window(
            path,
            start_seconds=max(0.0, position),
            duration_seconds=window_seconds,
            timeout=timeout_per_window,
        )
        checkpoints.append(
            DecodeCheckpoint(
                name=name,
                position_seconds=max(0.0, position),
                duration_seconds=window_seconds,
                ok=ok,
                error=error,
            )
        )

    measurements, reasons, hard_timing_fail = _duration_measurements(duration, expected_duration)
    failed_points = [item.name for item in checkpoints if not item.ok]
    if failed_points:
        reasons.append(f"decode failed at checkpoints: {', '.join(failed_points)}")

    if hard_timing_fail or failed_points:
        status = EvidenceStatus.FAIL
    else:
        status = EvidenceStatus.REVIEW
        reasons.append("three-point validation only; full decode not performed")

    measurements["checkpoint_count"] = len(checkpoints)
    measurements["checkpoint_failures"] = len(failed_points)
    return MediaQCReport(
        path=path.resolve(),
        mode="three-point",
        decision=QCDecision(status, tuple(reasons), measurements),
        probe=probe,
        checkpoints=tuple(checkpoints),
    )


def full_decode_check(
    path: Path,
    *,
    expected_duration: float | None = None,
    reconstruction_ambiguous: bool = False,
    reconstruction_unresolved: bool = False,
    timeout: float | None = None,
) -> MediaQCReport:
    """Decode the complete first video stream and combine media/reconstruction evidence.

    PASS is possible only when the full decode succeeds, an expected duration is
    supplied and acceptable, and reconstruction is neither ambiguous nor unresolved.
    """

    path = path.expanduser().resolve()
    probe = probe_video(path)
    reasons: list[str] = []
    measurements, duration_reasons, hard_timing_fail = _duration_measurements(
        probe.duration,
        expected_duration,
    )
    reasons.extend(duration_reasons)

    if probe.codec is None:
        reasons.append("no video stream detected")
        return MediaQCReport(
            path=path,
            mode="full-decode",
            decision=QCDecision(EvidenceStatus.FAIL, tuple(reasons), measurements),
            probe=probe,
        )

    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-i",
                str(path),
                "-map",
                "0:v:0",
                "-f",
                "null",
                "-",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
        decode_error = proc.stderr.strip()
        decode_failed = proc.returncode != 0 or bool(decode_error)
    except subprocess.TimeoutExpired as exc:
        decode_error = f"full decode timed out after {exc.timeout} seconds"
        decode_failed = True

    if decode_failed:
        reasons.append("full video decode reported errors")
    if reconstruction_ambiguous:
        reasons.append("reconstruction contains ambiguous continuation evidence")
    if reconstruction_unresolved:
        reasons.append("reconstruction contains unresolved continuation evidence")

    if decode_failed or hard_timing_fail:
        status = EvidenceStatus.FAIL
    elif reconstruction_ambiguous or reconstruction_unresolved:
        status = EvidenceStatus.REVIEW
    elif expected_duration is None or probe.duration is None:
        status = EvidenceStatus.REVIEW
    elif reasons:
        # Small timing deviation and similar soft conditions remain REVIEW.
        status = EvidenceStatus.REVIEW
    else:
        status = EvidenceStatus.PASS

    measurements["full_decode_completed"] = not decode_failed
    return MediaQCReport(
        path=path,
        mode="full-decode",
        decision=QCDecision(status, tuple(reasons), measurements),
        probe=probe,
        full_decode_error=decode_error or None,
    )
