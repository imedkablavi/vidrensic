from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json

from vidrensic import media_cli


def _timeline_report(*, review: bool = False):
    return SimpleNamespace(
        artifact=Path("candidate.mp4"),
        duration_seconds=120.0,
        observed_duration_seconds=120.0,
        duration_delta_seconds=0.0,
        duration_confidence="Low" if review else "High",
        frame_count=3000,
        keyframe_count=120,
        inferred_frame_rate=25.0,
        pts_non_monotonic=1 if review else 0,
        dts_non_monotonic=0,
        duplicate_pts=0,
        large_gaps=0,
        truncated=False,
        sha256="a" * 64,
        sha512="b" * 128,
        write_json=lambda output, replace=False: output,
        to_dict=lambda: {
            "schema_version": 1,
            "timeline": {
                "frame_count": 3000,
                "duration_confidence": "Low" if review else "High",
            },
        },
    )


def test_timeline_cli_is_clean_by_default(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "candidate.mp4"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(
        media_cli,
        "analyze_media_timeline",
        lambda *args, **kwargs: _timeline_report(),
    )

    assert media_cli.main([str(source), "--out", str(tmp_path / "timeline.json"), "--timeline"]) == 0
    output = capsys.readouterr().out
    assert "Timeline analysis complete" in output
    assert "Duration QC  High" in output
    assert "Timing       Stable" in output
    assert "PTS" not in output
    assert "DTS" not in output
    assert "sha256" not in output


def test_timeline_cli_surfaces_review_without_internal_numbers(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "candidate.mp4"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(
        media_cli,
        "analyze_media_timeline",
        lambda *args, **kwargs: _timeline_report(review=True),
    )

    assert media_cli.main([str(source), "--out", str(tmp_path / "timeline.json"), "--timeline"]) == 3
    output = capsys.readouterr().out
    assert "Duration QC  Low" in output
    assert "Timing       Review required" in output
    assert "1" in output
    assert "pts_non_monotonic" not in output


def test_timeline_cli_json_is_machine_readable(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "candidate.mp4"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(
        media_cli,
        "analyze_media_timeline",
        lambda *args, **kwargs: _timeline_report(),
    )

    assert media_cli.main(
        [str(source), "--out", str(tmp_path / "timeline.json"), "--timeline", "--json"]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["timeline"]["frame_count"] == 3000
    assert payload["timeline"]["duration_confidence"] == "High"
