from __future__ import annotations

from pathlib import Path
import json
from types import SimpleNamespace

from vidrensic import media_cli


def _report(path: Path, qc: dict | None = None):
    return SimpleNamespace(
        artifact=path,
        duration_seconds=65.0,
        video_codec="hevc",
        width=1920,
        height=1080,
        avg_frame_rate=25.0,
        stream_count=2,
        qc=qc,
        to_dict=lambda: {
            "schema_version": 1,
            "artifact": str(path),
            "hashes": {"sha256": "a" * 64, "sha512": "b" * 128},
        },
        write_json=lambda output, replace=False: output,
    )


def test_media_cli_is_concise_by_default(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "recovered.mp4"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(media_cli, "inspect_media", lambda *args, **kwargs: _report(source))

    assert media_cli.main([str(source), "--out", str(tmp_path / "inventory.json")]) == 0
    output = capsys.readouterr().out
    assert "Media inspection complete" in output
    assert "Stable during inspection" in output
    assert "ffprobe" not in output
    assert "sha256=" not in output


def test_media_cli_json_preserves_machine_readable_output(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "recovered.mp4"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(media_cli, "inspect_media", lambda *args, **kwargs: _report(source))

    assert media_cli.main([str(source), "--out", str(tmp_path / "inventory.json"), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["hashes"]["sha256"] == "a" * 64


def test_media_cli_qc_review_returns_nonzero(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "recovered.mp4"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(
        media_cli,
        "inspect_media",
        lambda *args, **kwargs: _report(
            source,
            {"status": "REVIEW"},
        ),
    )

    assert media_cli.main([str(source), "--out", str(tmp_path / "inventory.json"), "--qc", "fast"]) == 3
    assert "Review required" in capsys.readouterr().out


def test_media_cli_decoder_error_regions(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "recovered.mp4"
    source.write_bytes(b"fixture")
    region = SimpleNamespace(start_seconds=8.0, end_seconds=12.0, failed_windows=2)
    report = SimpleNamespace(
        artifact=source,
        duration_seconds=65.0,
        window_count=17,
        failed_window_count=2,
        coverage_fraction=1.0,
        sampling_complete=True,
        regions=(region,),
        sha256="a" * 64,
        sha512="b" * 128,
        to_dict=lambda: {
            "schema_version": 1,
            "decoder_errors": {"failed_window_count": 2, "region_count": 1},
        },
        write_json=lambda output, replace=False: output,
    )
    monkeypatch.setattr(media_cli, "analyze_decoder_error_regions", lambda *args, **kwargs: report)

    assert media_cli.main(
        [str(source), "--out", str(tmp_path / "errors.json"), "--decoder-errors"]
    ) == 3
    output = capsys.readouterr().out
    assert "Decoder error analysis complete" in output
    assert "Review required" in output
    assert "00:08" in output
