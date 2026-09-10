from __future__ import annotations

import json
from pathlib import Path

import pytest

from vidrensic.core.case import Case
from vidrensic.media.review_timeline import ReviewTimelineError, build_review_timeline
from vidrensic.review_cli import main


SHA256 = "a" * 64
OTHER_SHA256 = "b" * 64


def _case(tmp_path: Path) -> Case:
    return Case.create(tmp_path, "timeline-case", examiner="examiner")


def _artifact(case: Case) -> Path:
    path = case.root / "derived" / "review" / "clip.mp4"
    path.write_bytes(b"video")
    return path


def _timeline_report(case: Case, artifact: Path, sha256: str = SHA256) -> Path:
    path = case.root / "reports" / "timeline.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact": str(artifact),
                "hashes": {"sha256": sha256, "sha512": "c" * 128},
                "timeline": {
                    "duration_seconds": 20.0,
                    "observed_duration_seconds": 20.1,
                    "duration_delta_seconds": 0.1,
                    "duration_confidence": "High",
                    "frame_count": 600,
                    "keyframe_count": 20,
                    "keyframes_seconds": [0.0, 5.0, 10.0],
                    "inferred_frame_rate": 30.0,
                    "frame_rate_confidence": "High",
                    "pts_non_monotonic": 0,
                    "dts_non_monotonic": 0,
                    "duplicate_pts": 0,
                    "large_gaps": 1,
                    "truncated": False,
                    "anomalies": [{"frame": 301, "kind": "large-gap", "delta": 1.0}],
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _decoder_report(case: Case, artifact: Path, sha256: str = SHA256) -> Path:
    path = case.root / "reports" / "decoder.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact": str(artifact),
                "hashes": {"sha256": sha256, "sha512": "d" * 128},
                "decoder_errors": {
                    "duration_seconds": 20.0,
                    "window_seconds": 4.0,
                    "stride_seconds": 4.0,
                    "window_count": 5,
                    "failed_window_count": 1,
                    "coverage_fraction": 1.0,
                    "sampling_complete": True,
                    "regions": [
                        {
                            "start_seconds": 8.0,
                            "end_seconds": 12.0,
                            "failed_windows": 1,
                            "diagnostic": "decode error",
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_build_review_timeline_merges_hash_bound_sources(tmp_path: Path) -> None:
    case = _case(tmp_path)
    artifact = _artifact(case)
    item = case.review.register_item(artifact, SHA256, duration_seconds=20)
    case.review.add_bookmark(
        item.item_id,
        timestamp_seconds=5.0,
        expected_sha256=SHA256,
        label="event",
    )

    contract = build_review_timeline(
        case,
        item.item_id,
        _timeline_report(case, artifact),
        decoder_report_path=_decoder_report(case, artifact),
    )
    payload = contract.to_dict()

    assert payload["contract"]["kind"] == "review-timeline"
    assert payload["media"]["sha256"] == SHA256
    assert payload["timeline"]["keyframes_seconds"] == [0.0, 5.0, 10.0]
    assert payload["decoder_errors"]["failed_window_count"] == 1
    assert payload["bookmarks"][0]["label"] == "event"
    assert payload["bindings"]["hash_bound"] is True

    output = case.root / "reports" / "review-timeline.json"
    contract.write_json(output)
    assert output.is_file()


def test_build_review_timeline_rejects_mismatched_report_sha(tmp_path: Path) -> None:
    case = _case(tmp_path)
    artifact = _artifact(case)
    item = case.review.register_item(artifact, SHA256)

    with pytest.raises(ReviewTimelineError, match="SHA-256"):
        build_review_timeline(case, item.item_id, _timeline_report(case, artifact, OTHER_SHA256))


def test_build_review_timeline_rejects_report_outside_case(tmp_path: Path) -> None:
    case = _case(tmp_path)
    artifact = _artifact(case)
    item = case.review.register_item(artifact, SHA256)
    outside = tmp_path / "outside.json"
    outside.write_text(
        json.dumps(
            {
                "artifact": str(artifact),
                "hashes": {"sha256": SHA256},
                "timeline": {"keyframes_seconds": [], "anomalies": []},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReviewTimelineError, match="inside the case root"):
        build_review_timeline(case, item.item_id, outside)


def test_review_cli_timeline_exports_contract(tmp_path: Path, capsys) -> None:
    case = _case(tmp_path)
    artifact = _artifact(case)
    item = case.review.register_item(artifact, SHA256)
    timeline = _timeline_report(case, artifact)
    output = case.root / "reports" / "cli-review-timeline.json"

    assert main(
        [
            "timeline",
            "--case",
            str(case.root),
            "--item",
            item.item_id,
            "--timeline-report",
            str(timeline),
            "--out",
            str(output),
        ]
    ) == 0
    assert "Review timeline created" in capsys.readouterr().out
    assert json.loads(output.read_text(encoding="utf-8"))["contract"]["kind"] == "review-timeline"
