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
