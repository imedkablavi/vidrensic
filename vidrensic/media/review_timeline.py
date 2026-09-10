from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from vidrensic.core.case import Case
from vidrensic.core.json_limits import BoundedJSONError, load_bounded_json
from vidrensic.core.private_io import atomic_write_private_json


MAX_REPORT_BYTES = 64 * 1024 * 1024
MAX_DEPTH = 16
MAX_NODES = 250_000
MAX_STRING_CHARS = 64 * 1024
MAX_MARKERS = 100_000


class ReviewTimelineError(RuntimeError):
    """Raised when media reports cannot be safely combined for review."""


@dataclass(frozen=True)
class ReviewTimelineContract:
    item: dict[str, Any]
    media: dict[str, Any]
    timeline: dict[str, Any]
    decoder_errors: dict[str, Any] | None
    bookmarks: tuple[dict[str, Any], ...]
    bindings: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "contract": {
                "kind": "review-timeline",
                "derived": True,
                "description": "UI-neutral review timeline combining hash-bound media timing, decoder regions and analyst state",
            },
            "item": self.item,
            "media": self.media,
            "timeline": self.timeline,
            "decoder_errors": self.decoder_errors,
            "bookmarks": list(self.bookmarks),
            "bindings": self.bindings,
        }

    def write_json(self, output: Path, *, replace: bool = False) -> Path:
        return atomic_write_private_json(output, self.to_dict(), allow_replace=replace)


def _load_report(path: Path) -> dict[str, Any]:
    try:
        data = load_bounded_json(
            path.expanduser(),
            max_bytes=MAX_REPORT_BYTES,
            max_depth=MAX_DEPTH,
            max_nodes=MAX_NODES,
            max_string_chars=MAX_STRING_CHARS,
            label="media report",
        )
    except BoundedJSONError as exc:
        raise ReviewTimelineError(str(exc)) from exc
    if not isinstance(data, dict):
        raise ReviewTimelineError("media report must be a JSON object")
    return data


def _report_binding(path: Path, report: dict[str, Any]) -> dict[str, Any]:
    artifact = report.get("artifact")
    hashes = report.get("hashes")
    if not isinstance(artifact, str) or not isinstance(hashes, dict):
        raise ReviewTimelineError("media report is missing artifact/hash binding")
    sha256 = hashes.get("sha256")
    if not isinstance(sha256, str) or len(sha256) != 64:
        raise ReviewTimelineError("media report contains an invalid SHA-256 binding")
    return {
        "report_path": str(path.expanduser().resolve(strict=True)),
        "artifact": artifact,
        "artifact_sha256": sha256.lower(),
    }


def _same_artifact(item_sha256: str, report: dict[str, Any], *, label: str) -> None:
    hashes = report.get("hashes")
    if not isinstance(hashes, dict) or hashes.get("sha256", "").lower() != item_sha256:
        raise ReviewTimelineError(f"{label} SHA-256 does not match the registered review item")


def _timeline_payload(report: dict[str, Any]) -> dict[str, Any]:
    timeline = report.get("timeline")
    if not isinstance(timeline, dict):
        raise ReviewTimelineError("timeline report is missing the timeline object")
    anomalies = timeline.get("anomalies", [])
    keyframes = timeline.get("keyframes_seconds", [])
    if not isinstance(anomalies, list) or not isinstance(keyframes, list):
        raise ReviewTimelineError("timeline report has invalid marker collections")
    if len(anomalies) > MAX_MARKERS or len(keyframes) > MAX_MARKERS:
        raise ReviewTimelineError("timeline report exceeds the review marker safety limit")
    return timeline


def _decoder_payload(report: dict[str, Any]) -> dict[str, Any]:
    payload = report.get("decoder_errors")
    if not isinstance(payload, dict):
        raise ReviewTimelineError("decoder report is missing decoder_errors")
    regions = payload.get("regions", [])
    if not isinstance(regions, list) or len(regions) > MAX_MARKERS:
        raise ReviewTimelineError("decoder report has an invalid region collection")
    return payload


def build_review_timeline(
    case: Case,
    item_id: str,
    timeline_report_path: Path,
    *,
    decoder_report_path: Path | None = None,
) -> ReviewTimelineContract:
    """Combine hash-bound media analysis and analyst review state into one UI contract."""

    item = case.review.get_item(item_id)
    timeline_path = timeline_report_path.expanduser().resolve(strict=True)
    timeline_report = _load_report(timeline_path)
    _same_artifact(item.artifact_sha256, timeline_report, label="timeline report")
    timeline_binding = _report_binding(timeline_path, timeline_report)

    decoder_payload: dict[str, Any] | None = None
    decoder_binding: dict[str, Any] | None = None
    if decoder_report_path is not None:
        decoder_path = decoder_report_path.expanduser().resolve(strict=True)
        decoder_report = _load_report(decoder_path)
        _same_artifact(item.artifact_sha256, decoder_report, label="decoder report")
        decoder_payload = _decoder_payload(decoder_report)
        decoder_binding = _report_binding(decoder_path, decoder_report)

    timeline_payload = _timeline_payload(timeline_report)
    bookmarks = tuple(bookmark.to_dict() for bookmark in case.review.list_bookmarks(item_id))
    if len(bookmarks) > MAX_MARKERS:
        raise ReviewTimelineError("review bookmarks exceed the timeline safety limit")

    item_payload = item.to_dict()
    media = {
        "artifact": str(item.artifact),
        "sha256": item.artifact_sha256,
        "kind": item.kind,
        "duration_seconds": item.duration_seconds,
    }
    bindings = {
        "review_item_sha256": item.artifact_sha256,
        "timeline_report": timeline_binding,
        "decoder_report": decoder_binding,
        "hash_bound": True,
    }
    return ReviewTimelineContract(
        item=item_payload,
        media=media,
        timeline=timeline_payload,
        decoder_errors=decoder_payload,
        bookmarks=bookmarks,
        bindings=bindings,
    )
