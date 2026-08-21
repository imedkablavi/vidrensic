from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import median


EPOCH = datetime(2000, 1, 1)


@dataclass(frozen=True)
class NativeTimestampEvidence:
    decoded_local: datetime | None
    raw_value: str
    source_kind: str
    timezone_name: str | None = None
    confidence: float = 1.0
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("timestamp confidence must be between 0 and 1")
        if self.decoded_local is not None and self.decoded_local.tzinfo is not None:
            raise ValueError("decoded_local must be recorder-local naive time; timezone evidence is separate")

    def to_dict(self) -> dict:
        return {
            "decoded_local": self.decoded_local.isoformat() if self.decoded_local else None,
            "raw_value": self.raw_value,
            "source_kind": self.source_kind,
            "timezone_name": self.timezone_name,
            "confidence": self.confidence,
            "notes": list(self.notes),
            "classification": "NATIVE",
        }


@dataclass(frozen=True)
class ClockAnchor:
    recorder_local: datetime
    reference_utc: datetime
    source: str

    def __post_init__(self) -> None:
        if self.recorder_local.tzinfo is not None:
            raise ValueError("recorder_local anchor must be naive")
        if self.reference_utc.tzinfo is None:
            raise ValueError("reference_utc anchor must be timezone-aware")


@dataclass(frozen=True)
class ClockModel:
    slope: float
    intercept_seconds: float
    drift_ppm: float
    anchor_count: int
    residual_seconds: tuple[float, ...]
    max_abs_residual_seconds: float
    method: str
    status: str
    reasons: tuple[str, ...]

    def correct(self, recorder_local: datetime) -> datetime:
        if recorder_local.tzinfo is not None:
            raise ValueError("recorder_local must be naive")
        recorder_seconds = (recorder_local - EPOCH).total_seconds()
        reference_seconds = self.intercept_seconds + self.slope * recorder_seconds
        return datetime(2000, 1, 1, tzinfo=UTC) + timedelta(seconds=reference_seconds)

    def to_dict(self) -> dict:
        return {
            "slope": self.slope,
            "intercept_seconds": self.intercept_seconds,
            "drift_ppm": self.drift_ppm,
            "anchor_count": self.anchor_count,
            "residual_seconds": list(self.residual_seconds),
            "max_abs_residual_seconds": self.max_abs_residual_seconds,
            "method": self.method,
            "status": self.status,
            "reasons": list(self.reasons),
            "classification": "DERIVED",
        }


def _local_seconds(value: datetime) -> float:
    return (value - EPOCH).total_seconds()


def _utc_seconds(value: datetime) -> float:
    return (value.astimezone(UTC) - datetime(2000, 1, 1, tzinfo=UTC)).total_seconds()


def fit_clock_model(
    anchors: list[ClockAnchor] | tuple[ClockAnchor, ...],
    *,
    residual_review_threshold_seconds: float = 2.0,
    max_abs_drift_ppm: float = 50_000.0,
) -> ClockModel:
    """Fit a robust linear recorder-clock -> UTC model from explicit anchors.

    One anchor produces offset-only correction (slope 1). Two or more anchors use
    the median of all pairwise slopes (Theil-Sen style) and median intercept. No
    timezone/DST assumption is invented; anchors are examiner/evidence inputs.
    """

    if not anchors:
        raise ValueError("at least one clock anchor is required")
    if residual_review_threshold_seconds < 0 or max_abs_drift_ppm <= 0:
        raise ValueError("clock-model thresholds must be positive")

    points = [(_local_seconds(item.recorder_local), _utc_seconds(item.reference_utc)) for item in anchors]
    if len(points) == 1:
        slope = 1.0
        intercept = points[0][1] - points[0][0]
        method = "single-anchor-offset"
    else:
        slopes: list[float] = []
        for index, (x1, y1) in enumerate(points):
            for x2, y2 in points[index + 1 :]:
                if x2 == x1:
                    continue
                slopes.append((y2 - y1) / (x2 - x1))
        if not slopes:
            raise ValueError("clock anchors do not span distinct recorder times")
        slope = median(slopes)
        intercept = median(y - slope * x for x, y in points)
        method = "median-pairwise-slope"

    residuals = tuple(y - (intercept + slope * x) for x, y in points)
    max_residual = max(abs(value) for value in residuals)
    drift_ppm = (slope - 1.0) * 1_000_000.0
    reasons: list[str] = []
    if abs(drift_ppm) > max_abs_drift_ppm:
        reasons.append(f"estimated clock drift {drift_ppm:.1f} ppm exceeds configured plausibility bound")
    if max_residual > residual_review_threshold_seconds:
        reasons.append(
            f"anchor residual {max_residual:.3f}s exceeds {residual_review_threshold_seconds:.3f}s review threshold"
        )
    if len(points) == 1:
        reasons.append("single anchor cannot establish clock drift; slope is fixed to 1")

    return ClockModel(
        slope=slope,
        intercept_seconds=intercept,
        drift_ppm=drift_ppm,
        anchor_count=len(points),
        residual_seconds=residuals,
        max_abs_residual_seconds=max_residual,
        method=method,
        status="REVIEW" if reasons else "PASS",
        reasons=tuple(reasons),
    )
